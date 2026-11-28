"""Stage 2 evaluation (protocol 1.10 sections 4, 5, 8, 9), in three separate modes so that no score is computed before
the step that reports it (HANDOFF "Do not"; checkpoint 04 is a stop before 2026):
  build     build the layers from the members, calibrate in time order (section 8) and score targets in 2023-2024 only.
            Writes chosen_layer.json = layer b, labelled as the fallback before the 2025 layer test (HANDOFF addition 2).
  test2025  the layer rule on 2025 (section 9), dollar-weighted coverage for 2025 and for each half (section 6a), the
            unit breaks inside 2025-26 beside the score, and 28081 scored on its own (ruling 01b amendment item 6).
  test2026  the 2026 test, reported once, with and without open handover windows. Refuses to run without
            ruling-04.md in the handoff folder, or if stage2/test_2026.csv already exists.
Layers: (a) seasonal naive; (b) per-series statistical pool; (c) pool members + the global tree model, equal weights;
(d) (c) with split conformal calibration per class and horizon on scaled errors.
Usage: python s2eval.py <base> <build|test2025|test2026> [calibration window months, default 12]"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q, H, metric, block_bootstrap, pinball, SEPARATE

QC = [f"q{int(round(q * 100)):02d}" for q in Q]
POOL = {"regular": ["ets"], "intermittent": ["sba", "tsb", "adida"], "new": ["own_mean"]}
HANDOFF = Path(r"<home>\OneDrive\Desktop\Claude_Allowed\iowa-handoff")
FLAG_SEPARATE = SEPARATE        # 87035 and 28081: out of the selection metric and headline score (ruling 01d B6)


def load(base):
    m = pd.concat([pd.read_parquet(f) for f in sorted((base / "stage2" / "members").glob("members_*.parquet"))])
    tdir = base / "stage2" / "tree"
    tree = (pd.concat([pd.read_parquet(f) for f in sorted(tdir.glob("tree_fit*.parquet"))]) if tdir.exists() and
            any(tdir.glob("tree_fit*.parquet")) else None)
    if tree is not None:
        # an origin predicted by two fits (the live origin) takes the later fit
        tree["fit"] = tree.groupby(["sid", "o", "h"]).cumcount()
        tree = tree.sort_values("fit").drop_duplicates(["sid", "o", "h"], keep="last").drop(columns="fit")
    return m, tree


def layers(m, tree):
    cls = m[["sid", "o", "pool_class", "sbc_class"]].drop_duplicates(["sid", "o"])
    a = m[m.member == "seasonal_naive"].assign(layer="a")
    stat = m[m.member.isin(sum(POOL.values(), []))]
    b = stat.groupby(["sid", "o", "h"])[["mean"] + QC].mean().reset_index().assign(layer="b")
    out = [a[["sid", "o", "h", "layer", "mean"] + QC], b]
    if tree is not None:
        t = tree.merge(cls[["sid", "o"]], on=["sid", "o"])      # only series the stat side forecasts
        c = pd.concat([stat[["sid", "o", "h", "mean"] + QC], t[["sid", "o", "h", "mean"] + QC]])
        c = c.groupby(["sid", "o", "h"])[["mean"] + QC].mean().reset_index().assign(layer="c")
        out.append(c)
    L = pd.concat(out, ignore_index=True)
    L[QC] = np.sort(np.maximum(L[QC].to_numpy(), 0), axis=1)
    return L.merge(cls, on=["sid", "o"], how="left")


def calibrate(d, L, src, window):
    """split conformal per quantile, pooled within pool class, per horizon, on scaled errors of layer `src` over the
    `window` most recent target months already observed at each origin (only past targets are used)."""
    x = L[L.layer == src].copy()
    sc = {o: d.scale(o) for o in x.o.unique()}
    x["s"] = [sc[o][s] for s, o in zip(x.sid, x.o)]
    x["t"] = x.o + x.h
    x["y"] = [d.Y[s, t] if t < d.M else np.nan for s, t in zip(x.sid, x.t)]
    ok = x.y.notna() & np.isfinite(x.s) & (x.s > 0)
    R = pd.DataFrame({c: (x.y - x[c]) / x.s for c in QC})[ok]
    R[["o", "h", "t", "pool_class"]] = x.loc[ok, ["o", "h", "t", "pool_class"]]
    out = []
    for (o, h, cl), g in x.groupby(["o", "h", "pool_class"]):
        r = R[(R.h == h) & (R.pool_class == cl) & (R.t <= o) & (R.t > o - window)]
        g = g.copy()
        if len(r) >= 19:
            adj = np.array([np.quantile(r[c], q) for c, q in zip(QC, Q)])
            s_ = np.where(np.isfinite(g.s) & (g.s > 0), g.s, 0)
            g[QC] = np.sort(np.maximum(g[QC].to_numpy() + adj[None, :] * s_[:, None], 0), axis=1)
            g["calibrated"] = True
        else:
            g["calibrated"] = False
        out.append(g)
    c = pd.concat(out)
    c["layer"] = "d"
    return c.drop(columns=["s", "t", "y"])


def target_year(d, L):
    t = (L.o + L.h).to_numpy()
    return np.array([d.months[k].year if k < d.M else 9999 for k in t])


def coverage(d, L, years, months=None):
    rows = []
    for (lay, o, h), g in L.groupby(["layer", "o", "h"]):
        t = o + h
        if t >= d.M or d.months[t].year not in years or (months is not None and d.months[t].month not in months):
            continue
        y = d.Y[g.sid.to_numpy(), t]
        ok = ~np.isnan(y) & d.active(o)[g.sid.to_numpy()] & ~d.open_handover(o)[g.sid.to_numpy()]
        w = d.weight12(o)[g.sid.to_numpy()]
        for cl in ["all"] + sorted(g.pool_class.dropna().unique()):
            m = ok & ((g.pool_class.to_numpy() == cl) if cl != "all" else True)
            if not m.any() or w[m].sum() == 0:
                continue
            ww = w[m] / w[m].sum(); yy = y[m]
            rows.append(dict(layer=lay, o=o, h=h, cls=cl,
                             in90=float((ww * ((yy >= g.q05.to_numpy()[m]) & (yy <= g.q95.to_numpy()[m]))).sum()),
                             in50=float((ww * ((yy >= g.q25.to_numpy()[m]) & (yy <= g.q75.to_numpy()[m]))).sum()),
                             above95=float((ww * (yy > g.q95.to_numpy()[m])).sum()),
                             below05=float((ww * (yy < g.q05.to_numpy()[m])).sum())))
    return pd.DataFrame(rows)


def layer_test(mt, simple, complex_, year=2025):
    x = mt[(mt.set == "excl_open") & (mt.year == year)]
    a = x[x.layer == simple].groupby("t").loss.mean(); b = x[x.layer == complex_].groupby("t").loss.mean()
    j = pd.concat([a, b], axis=1, keys=["s", "c"]).dropna()
    if j.empty:
        return None
    s3 = x[x.layer == simple].groupby("h").loss.mean().mean(); c3 = x[x.layer == complex_].groupby("h").loss.mean().mean()
    gain = 1 - c3 / s3
    boot = block_bootstrap((j.s - j.c).to_numpy())
    return dict(simple=simple, complex=complex_, simple_loss=s3, complex_loss=c3, gain_pct=100 * gain,
                boot_share=boot, passes=bool(gain >= 0.02 and boot >= 0.90))


def flagged_scores(d, L, year):
    """scaled pinball per layer and horizon for the flagged series scored on their own (ruling 01b amendment item 6)"""
    rows = []
    for it in FLAG_SEPARATE:
        hit = np.flatnonzero(d.sids == it)
        if not len(hit):
            continue
        s = hit[0]
        g = L[(L.sid == s)]
        for r in g.itertuples():
            t = r.o + r.h
            if t >= d.M or d.months[t].year != year or np.isnan(d.Y[s, t]):
                continue
            sc = d.scale(r.o)[s]
            loss = pinball(np.array([d.Y[s, t]]), np.array([[getattr(r, c) for c in QC]]))[0] / (sc if sc > 0 else 1)
            w = d.weight12(r.o); share = w[s] / w[d.active(r.o)].sum()
            rows.append(dict(series_id=it, layer=r.layer, o=r.o, h=r.h, t=str(d.months[t]), scaled_pinball=loss,
                             share_of_trailing_dollars=share))
    return pd.DataFrame(rows)


def breaks_in(base, years):
    ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str}, parse_dates=["month"])
    return ap[ap.month.dt.year.isin(years)][["item_no", "month", "pack_old", "pack_new", "factor", "action", "outcome", "usd_t12"]]


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    base = Path(sys.argv[1]); mode = sys.argv[2]; window = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    out = base / "stage2"
    d = Data(base)
    if mode == "build":
        m, tree = load(base)
        L = layers(m, tree)
        top = "c" if tree is not None else "b"
        L = pd.concat([L, calibrate(d, L, top, window)], ignore_index=True)
        L.to_parquet(out / "layers.parquet", index=False)
        ty = target_year(d, L)
        mt = metric(d, L[np.isin(ty, [2023, 2024])])                # choice years only; 2025-26 are not scored here
        mt.to_csv(out / "metric_2023_24.csv", index=False)
        summ = mt[mt.set.isin(["excl_open", "excl_open_excl_window"])].groupby(["set", "year", "layer", "h"]).loss.mean().unstack("h")
        summ["mean_h1_3"] = summ.mean(axis=1)
        summ.to_csv(out / "metric_summary_2023_24.csv")
        win_items = sorted(set(d.sids[np.flatnonzero(d.window.any(1))]))
        print("selection metric on 2023-2024 targets (excl. open handover windows; set 'excl_window' also leaves out the "
              f"unit_change_window item-months of {len(win_items)} restated items: {', '.join(win_items)}; flattered if tuned):")
        print(summ.round(4).to_string())
        fs = flagged_scores(d, L, 2023); fs = pd.concat([fs, flagged_scores(d, L, 2024)])
        fs.to_csv(out / "flagged_scores_2023_24.csv", index=False)
        json.dump({"chosen_layer": "b", "calibration_window": window,
                   "status": "fallback before the 2025 layer test: baseline per-series pool (layer b)"},
                  open(out / "chosen_layer.json", "w"))
    elif mode == "test2025":
        L = pd.read_parquet(out / "layers.parquet")
        ty = target_year(d, L)
        mt = metric(d, L[ty == 2025])
        mt.to_csv(out / "metric_2025.csv", index=False)
        tree = (L.layer == "c").any()
        chosen, tests = "a", []
        for cx in (["b", "c", "d"] if tree else ["b"]):
            t = layer_test(mt, chosen, cx)
            if t is None:
                continue
            tests.append(t)
            print(f"layer {t['complex']} vs {t['simple']} on 2025: gain {t['gain_pct']:+.2f}%, bootstrap {100 * t['boot_share']:.1f}% "
                  f"-> {'passes' if t['passes'] else 'fails'}")
            if t["passes"]:
                chosen = cx
        pd.DataFrame(tests).to_csv(out / "layer_tests_2025.csv", index=False)
        cov = []
        for name, mon in (("2025", None), ("2025 H1", range(1, 7)), ("2025 H2", range(7, 13))):
            c = coverage(d, L, {2025}, mon).assign(period=name); cov.append(c)
        cov = pd.concat(cov)
        cv = cov.groupby(["period", "layer", "cls", "h"])[["in90", "in50", "above95", "below05"]].mean().reset_index()
        cv.to_csv(out / "coverage_2025.csv", index=False)
        pooled = cov[cov.cls == "all"].groupby(["period", "layer"])[["in90", "in50"]].mean()
        print("2025 dollar-weighted coverage (90% band 85-95, 50% band 44-56), by period:")
        print((100 * pooled).round(1).to_string())
        if chosen == "d":
            p = pooled.loc[("2025", "d")]
            print("coverage check on the chosen calibrated layer:",
                  "pass" if 0.85 <= p.in90 <= 0.95 and 0.44 <= p.in50 <= 0.56 else "FAIL (named retry: rerun with window 24)")
        fs = flagged_scores(d, L, 2025); fs.to_csv(out / "flagged_scores_2025.csv", index=False)
        if len(fs):
            print("scored separately (28081):"); print(fs.groupby(["layer", "h"]).scaled_pinball.mean().unstack("h").round(4).to_string())
        bk = breaks_in(base, [2025, 2026]); bk.to_csv(out / "unit_breaks_2025_26.csv", index=False)
        print(f"unit breaks inside 2025-26 (beside the test score): {len(bk)}"); print(bk.to_string(index=False))
        print("chosen layer:", chosen)
        json.dump({"chosen_layer": chosen, "calibration_window": window, "status": "after the 2025 layer test"},
                  open(out / "chosen_layer.json", "w"))
    elif mode == "test2026":
        if not (HANDOFF / "ruling-04.md").exists():
            sys.exit("test2026 needs ruling-04.md in the handoff folder (checkpoint 04 is a stop)")
        if (out / "test_2026.csv").exists():
            sys.exit("the 2026 test has already been reported once (stage2/test_2026.csv exists)")
        chosen = json.load(open(out / "chosen_layer.json"))["chosen_layer"]
        L = pd.read_parquet(out / "layers.parquet")
        ty = target_year(d, L)
        mt = metric(d, L[(ty == 2026) & (L.layer == chosen)])
        t26 = mt.groupby(["set", "h"]).loss.mean().unstack("h"); t26["mean_h1_3"] = t26.mean(axis=1)
        t26.to_csv(out / "test_2026.csv")
        print(f"2026 test, chosen layer {chosen} (with and without open handover windows):"); print(t26.round(4).to_string())
        fs = flagged_scores(d, L[L.layer == chosen], 2026); fs.to_csv(out / "flagged_scores_2026.csv", index=False)
        # ruling-04 item 2: chosen layer's 2026 dollar-weighted coverage by class, same function as 2025, report only
        cv = coverage(d, L[L.layer == chosen], {2026})
        cv.groupby(["layer", "cls", "h"])[["in90", "in50", "above95", "below05"]].mean().reset_index().to_csv(out / "coverage_2026.csv", index=False)
        print("2026 coverage, report only (in90 in50 above95 below05, %):")
        print((100 * cv.groupby("cls")[["in90", "in50", "above95", "below05"]].mean()).round(1).to_string())
        bk = breaks_in(base, [2025, 2026])
        print(f"unit breaks inside 2025-26: {len(bk)} (stage2/unit_breaks_2025_26.csv)")
    else:
        sys.exit(f"unknown mode {mode}")
