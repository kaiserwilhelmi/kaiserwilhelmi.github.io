"""Stage 2 global tree model (protocol 1.10 sections 6, 6a and 7; decision 56).
One LightGBM model per horizon (1, 2, 3 months ahead) across all series, on bottles per effective order day scaled by
each series' section 4 scale of the per-day series as of the yearly fit; one fit per quantile plus a Tweedie fit for
the mean. Fitted once per year on data through December and fed new months without refitting (section 7). Inputs are
only values known at the origin. Series with no scale at the fit are left out (they get the statistical members only).
Feature sets (section 6a, fixed): "base" = lags 1-13, rolling means and standard deviations over 3, 6 and 12 months,
target month, effective order days of the target month, category, vendor as of origin, class as of origin, months since
first order, average price stores paid per unit as of origin; "ext" = base + same-month values one and two years back
+ category-level rolling means (3 and 12 months).
Tuning (section 6a): targets in 2023 and 2024 only (fit through Dec 2022 -> 2023 targets; through Dec 2023 -> 2024).
Each trial fits three quantiles (0.10, 0.50, 0.90) per horizon and is scored on their mean pinball (the selection
metric's construction: scaled, dollar-weighted, excl. open handover windows, averaged over origins, mean of h1-3).
Boosting rounds: up to 2,000 per model, chosen on 2023 targets in the first fit (weighted validation loss, patience
100) and reused in the second fit; no fit ever sees 2025 or 2026 targets. Fixed seeds.
Usage:
  python s2tree.py <base> trial <settings json|start> <base|ext> [half]   one trial, appended to stage2/tree/trials.csv
  python s2tree.py <base> tune [hours cap, default 8]                     the whole section 6a plan
  python s2tree.py <base> run <settings json|start|chosen> <first fit year> <last fit year>   final fits (7 q + mean)"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import os, sys, json, time, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q, H, progress, scored_mask, pinball

QC = [f"q{int(round(q * 100)):02d}" for q in Q]
Q3 = np.array([0.10, 0.50, 0.90]); QC3 = ["q10", "q50", "q90"]
START = dict(num_leaves=63, min_data_in_leaf=100, learning_rate=0.05, feature_fraction=0.8, bagging_fraction=0.8,
             lambda_l2=1.0)
RANGES = dict(num_leaves=(15, 255, "log_int"), min_data_in_leaf=(20, 500, "log_int"), learning_rate=(0.02, 0.1, "log"),
              feature_fraction=(0.5, 1.0, "lin"), bagging_fraction=(0.5, 1.0, "lin"), lambda_l2=(0.0, 10.0, "lin"))
TWEEDIE = (1.1, 1.3, 1.5, 1.7)
MAX_ROUNDS, PATIENCE, SEED, TRIAL_SEED, HALF_SEED = 2000, 100, 20261128, 20261127, 20261126
FIRST_TRAIN_ORIGIN = 13          # Feb 2013: 13 months of lags
CAT = ["category", "vendor", "pool_class"]
OUT = None
PROXY_EXTRA = {}     # the last proxy score with unit_change_window item-months left out (shown, never used to choose)


def per_day_scale(d, cutoff):
    eff = d.eff_days(cutoff)
    X = d.hist(d.Y / eff[None, :d.M], cutoff)
    with np.errstate(all="ignore"):
        return np.nanmean(np.abs(np.diff(X, axis=1)), axis=1)


def price_asof(d, o):
    # average price stores paid per unit as of the origin: median of the monthly dollars / restated units over the last
    # 3 months with orders (section 1; decision 50: price = dollars over restated units)
    P = np.where(d.Y > 0, d.D / np.where(d.Y > 0, d.Y, 1), np.nan)
    P = np.where(d.cols[None, :] <= o, P, np.nan)
    out = np.full(d.S, np.nan)
    for s in range(d.S):
        v = P[s, :o + 1]; v = v[~np.isnan(v)][-3:]
        if len(v):
            out[s] = np.median(v)
    return out


def features(d, o, h, sc, pool, price, fset, keep_mask=None):
    """rows for series active at origin o with a scale at the fit; values per day, scaled; shares as of o."""
    eff = d.eff_days(o)
    t = o + h
    keep = (pool != "") & np.isfinite(sc) & (sc > 0)
    if keep_mask is not None:
        keep &= keep_mask
    s = np.flatnonzero(keep)
    Z = (d.Y[s] / eff[None, :d.M]) / sc[s, None]
    Z = np.where(d.cols[None, :] <= o, Z, np.nan)
    f = {"sid": s, "o": o, "h": h}
    for k in range(13):
        f[f"lag{k + 1}"] = Z[:, o - k] if o - k >= 0 else np.nan
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for w in (3, 6, 12):
            win = Z[:, max(o - w + 1, 0):o + 1]
            f[f"mean{w}"] = np.nanmean(win, axis=1); f[f"sd{w}"] = np.nanstd(win, axis=1)
    f["month"] = (d.months[0] + t).month
    f["eff_days_target"] = eff[t]
    f["months_since_first"] = o - d.first[s] + 1
    f["price"] = price[s]
    f["category"] = d.category[s]
    f["vendor"] = d.vendor_by_month[s, o]
    f["pool_class"] = pool[s]
    X = pd.DataFrame(f)
    if fset == "ext":
        X["same_month_1y"] = Z[:, t - 12] if t - 12 <= o else np.nan
        X["same_month_2y"] = Z[:, t - 24] if t - 24 >= 0 else np.nan
        for w in (3, 12):
            X[f"cat_mean{w}"] = X.groupby("category")[f"mean{w}"].transform("mean")
    if t < d.M:
        X["y"] = (d.Y[s, t] / eff[t]) / sc[s]
    X["eff_t"] = eff[t]
    return X


def build_rows(d, origins, sc, fset, keep_mask=None, with_y=True):
    parts = []
    for o in origins:
        pool, _ = d.classes(o)
        price = price_asof(d, o)
        for h in H:
            if with_y and o + h >= d.M:
                continue
            parts.append(features(d, o, h, sc, pool, price, fset, keep_mask))
    X = pd.concat(parts, ignore_index=True)
    for c in CAT:
        X[c] = X[c].astype("category")
    return X


def lgb_params(st, threads):
    p = dict(verbose=-1, num_threads=threads, seed=SEED, deterministic=True, bagging_freq=1,
             num_leaves=int(st["num_leaves"]), min_data_in_leaf=int(st["min_data_in_leaf"]),
             learning_rate=float(st["learning_rate"]), feature_fraction=float(st["feature_fraction"]),
             bagging_fraction=float(st["bagging_fraction"]), lambda_l2=float(st["lambda_l2"]))
    return p


def fit_models(d, cutoff, st, fset, threads, quantiles, rounds=None, valid_year=None, keep_mask=None, tweedie=None):
    """fits per horizon for the given quantiles (and a Tweedie mean when tweedie is a power). With rounds=None the rounds
    of each model are chosen on validation rows with targets in valid_year (weighted pinball, patience 100)."""
    import lightgbm as lgb
    sc = per_day_scale(d, cutoff)
    X = build_rows(d, range(FIRST_TRAIN_ORIGIN, cutoff), sc, fset, keep_mask)
    X = X[X.o + X.h <= cutoff].dropna(subset=["y"])
    feats = [c for c in X.columns if c not in ("sid", "o", "h", "y", "eff_t")]
    V = None
    if rounds is None:
        vy = d.mi[pd.Period(f"{valid_year}-01", "M")]
        V = build_rows(d, range(cutoff, cutoff + 12), sc, fset, keep_mask)
        V = V[(V.o + V.h >= vy) & (V.o + V.h <= vy + 11)].dropna(subset=["y"])
        w = d.weight12(cutoff)[V.sid.to_numpy()]
        V["w"] = w / w.sum()
    models, chosen = {}, {}
    base = lgb_params(st, threads)
    for h in H:
        Xh = X[X.h == h]
        ds = lgb.Dataset(Xh[feats], Xh.y, categorical_feature=CAT, free_raw_data=False)
        Vh = V[V.h == h] if V is not None else None
        dv = lgb.Dataset(Vh[feats], Vh.y, weight=Vh.w, categorical_feature=CAT, reference=ds) if Vh is not None else None
        jobs = [(f"q{int(round(q * 100)):02d}", {"objective": "quantile", "alpha": float(q), "metric": "quantile"}) for q in quantiles]
        if tweedie is not None:
            jobs.append(("mean", {"objective": "tweedie", "tweedie_variance_power": float(tweedie), "metric": "l2"}))
        for name, obj in jobs:
            if rounds is None:
                m = lgb.train({**base, **obj}, ds, MAX_ROUNDS, valid_sets=[dv],
                              callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
                chosen[(h, name)] = m.best_iteration or MAX_ROUNDS
            else:
                m = lgb.train({**base, **obj}, ds, int(rounds[(h, name)]))
                chosen[(h, name)] = int(rounds[(h, name)])
            models[(h, name)] = m
    return models, feats, sc, {c: X[c].cat.categories for c in CAT}, chosen


def predict(d, models, feats, sc, cats, origins, fset, keep_mask=None):
    X = build_rows(d, origins, sc, fset, keep_mask, with_y=False)
    for c in CAT:
        X[c] = pd.Categorical(X[c].astype(str), categories=cats[c])
    parts = []
    for h in H:
        Xh = X[X.h == h]
        if not len(Xh):
            continue
        out = Xh[["sid", "o", "h", "eff_t"]].copy()
        s_ = sc[Xh.sid.to_numpy()]
        for (hh, name), m in models.items():
            if hh == h:
                out[name] = np.maximum(m.predict(Xh[feats], num_iteration=m.best_iteration or None), 0) * s_ * out.eff_t
        parts.append(out)
    out = pd.concat(parts, ignore_index=True).drop(columns="eff_t")
    qs = [c for c in out.columns if c.startswith("q")]
    out[qs] = np.sort(out[qs].to_numpy(), axis=1)
    return out


def proxy_score(d, pred, years, qcols=QC3, qv=Q3, keep_mask=None):
    """selection metric construction on the given quantiles: per origin and horizon, scaled pinball weighted by trailing
    dollars over scored series (excl. open handover windows); averaged over origins, then over horizons; and per year."""
    rows = []
    for (o, h), g in pred.groupby(["o", "h"]):
        t = o + h
        if t >= d.M or d.months[t].year not in years:
            continue
        _, ok, sc = scored_mask(d, o, t)
        if keep_mask is not None:
            ok = ok & keep_mask
        sid = g.sid.to_numpy(); m = ok[sid]
        if not m.any():
            continue
        y = np.nan_to_num(d.Y[sid, t]); qf = g[qcols].to_numpy()
        dd = y[:, None] - qf
        L = np.where(dd >= 0, dd * qv, -dd * (1 - qv)).mean(1) / np.where(sc[sid] > 0, sc[sid], 1)
        w = d.weight12(o)[sid] * m
        mx = m & ~d.window[sid, t]; wx = d.weight12(o)[sid] * mx
        rows.append(dict(o=o, h=h, year=d.months[t].year, loss=float((w * L)[m].sum() / w.sum()),
                         loss_xw=float((wx * L)[mx].sum() / wx.sum()) if wx.sum() > 0 else np.nan))
    r = pd.DataFrame(rows)
    by_h = r.groupby("h").loss.mean()
    PROXY_EXTRA["score_excl_window"] = float(r.groupby("h").loss_xw.mean().mean())
    return float(by_h.mean()), {y: float(r[r.year == y].groupby("h").loss.mean().mean()) for y in years}


def mean_sq_error(d, pred, years):
    rows = []
    for (o, h), g in pred.groupby(["o", "h"]):
        t = o + h
        if t >= d.M or d.months[t].year not in years:
            continue
        _, ok, sc = scored_mask(d, o, t)
        sid = g.sid.to_numpy(); m = ok[sid]
        y = np.nan_to_num(d.Y[sid, t])
        E = ((y - g["mean"].to_numpy()) / np.where(sc[sid] > 0, sc[sid], 1)) ** 2
        w = d.weight12(o)[sid] * m
        rows.append(dict(o=o, h=h, loss=float((w * E)[m].sum() / w.sum())))
    return float(pd.DataFrame(rows).groupby("h").loss.mean().mean())


def half_mask(d):
    rng = np.random.default_rng(HALF_SEED)
    return rng.random(d.S) < 0.5


def run_trial(d, st, fset, threads, keep_mask=None, tweedie=None):
    """one section 6a trial: fit through Dec 2022 with rounds chosen on 2023 targets, reuse them in the fit through
    Dec 2023; score on 2023 and 2024 targets."""
    t0 = time.time(); preds = []; rounds = None
    for fy in (2022, 2023):
        cutoff = d.mi[pd.Period(f"{fy}-12", "M")]
        models, feats, sc, cats, chosen = fit_models(d, cutoff, st, fset, threads, Q3, rounds=rounds,
                                                     valid_year=2023 if rounds is None else None, keep_mask=keep_mask, tweedie=tweedie)
        rounds = chosen
        preds.append(predict(d, models, feats, sc, cats, range(cutoff, cutoff + 12), fset, keep_mask))
    p = pd.concat(preds, ignore_index=True)
    score, by_year = proxy_score(d, p, (2023, 2024), keep_mask=keep_mask)
    out = dict(score_h1_3=score, score_2023=by_year[2023], score_2024=by_year[2024],
               score_excl_window=PROXY_EXTRA.get("score_excl_window"), seconds=round(time.time() - t0),
               rounds=json.dumps({f"h{h}_{n}": int(r) for (h, n), r in rounds.items()}))
    if tweedie is not None:
        out["mean_sq_error"] = mean_sq_error(d, p, (2023, 2024))
    return out


def sample_settings(n):
    rng = np.random.default_rng(TRIAL_SEED)
    out = []
    for _ in range(n):
        st = {}
        for k, (lo, hi, kind) in RANGES.items():
            u = rng.random()
            if kind == "log_int":
                st[k] = int(round(np.exp(np.log(lo) + u * (np.log(hi) - np.log(lo)))))
            elif kind == "log":
                st[k] = float(np.exp(np.log(lo) + u * (np.log(hi) - np.log(lo))))
            else:
                st[k] = float(lo + u * (hi - lo))
        out.append(st)
    return out


def append_trial(row):
    f = OUT / "trials.csv"
    pd.DataFrame([row]).to_csv(f, mode="a", header=not f.exists(), index=False)


def load_settings(arg):
    if arg == "start":
        return dict(START)
    if arg == "chosen":
        return json.load(open(OUT / "chosen_config.json"))["settings"]
    return json.loads(arg) if arg.strip().startswith("{") else json.load(open(arg))


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    base = Path(sys.argv[1]); mode = sys.argv[2]
    threads = max(1, (os.cpu_count() or 2) - 2)
    OUT = base / "stage2" / "tree"; OUT.mkdir(parents=True, exist_ok=True)
    d = Data(base)
    if mode == "trial":
        st = load_settings(sys.argv[3]); fset = sys.argv[4]; half = len(sys.argv) > 5 and sys.argv[5] == "half"
        progress(base, f"tree trial: start ({fset}, {'half' if half else 'all'} series)")
        r = run_trial(d, st, fset, threads, half_mask(d) if half else None)
        row = dict(trial="timing", feature_set=fset, half=half, **st, **r); append_trial(row)
        progress(base, f"tree trial: done in {r['seconds']}s, proxy {r['score_h1_3']:.4f}")
        print({k: row[k] for k in ("seconds", "score_h1_3")})
    elif mode == "tune":
        cap_h = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
        t_all = time.time()
        # resume (ruling-02-resume, decision 67): every finished trial is already a row in trials.csv; skip those
        from trials_read import read_trials          # header predates score_excl_window; read by position
        prev = read_trials(OUT / "trials.csv") if (OUT / "trials.csv").exists() else pd.DataFrame(columns=["trial", "feature_set", "half"])
        prev["trial"] = prev.trial.astype(str)
        def done(label, fset, half):
            x = prev[(prev.trial == str(label)) & (prev.feature_set == fset) & (prev.half.astype(str) == str(half))]
            return x.iloc[-1].to_dict() if len(x) else None
        # feature set: the better of the two under the starting settings goes into the search
        fs_rows = []
        for fset in ("base", "ext"):
            row = done(f"featureset_{fset}", fset, False)
            if row is None:
                r = run_trial(d, START, fset, threads); row = dict(trial=f"featureset_{fset}", feature_set=fset, half=False, **START, **r)
                append_trial(row)
            else:
                progress(base, f"tree tune: feature set {fset} already done (resumed)")
            fs_rows.append(row)
            progress(base, f"tree tune: feature set {fset} proxy {row['score_h1_3']:.4f} ({row['seconds']}s)")
        fset = min(fs_rows, key=lambda x: x["score_h1_3"])["feature_set"]
        t_trial = np.mean([x["seconds"] for x in fs_rows])
        n_fit = int((cap_h * 3600 - (time.time() - t_all)) // t_trial)
        n_trials, half = min(40, n_fit), False
        if n_trials < 15:
            half = True; n_trials = 40 if n_fit * 2 >= 40 else max(15, min(40, n_fit * 2))
        keep = half_mask(d) if half else None
        progress(base, f"tree tune: feature set {fset}; {n_trials} random trials{' on a fixed-seed half of the series' if half else ''}")
        trial0 = next(x for x in fs_rows if x["feature_set"] == fset)
        if half:
            r = run_trial(d, START, fset, threads, keep); trial0 = dict(trial=0, feature_set=fset, half=True, **START, **r); append_trial(trial0)
        else:
            trial0 = dict(trial0, trial=0)
        res = [trial0]
        for i, st in enumerate(sample_settings(n_trials), 1):
            row = done(i, fset, half)
            if row is not None and all(np.isclose(float(row[k]), float(v)) for k, v in st.items()):
                res.append(row); progress(base, f"tree tune: trial {i} already done (resumed)"); continue
            r = run_trial(d, st, fset, threads, keep); row = dict(trial=i, feature_set=fset, half=half, **st, **r)
            append_trial(row); res.append(row)
            progress(base, f"tree tune: trial {i} proxy {r['score_h1_3']:.4f} ({r['seconds']}s)", i, n_trials, t_all)
        best = min(res, key=lambda x: x["score_h1_3"])
        gain = 1 - best["score_h1_3"] / trial0["score_h1_3"]
        adopt = bool(best["trial"] != 0 and gain >= 0.01 and best["score_2023"] < trial0["score_2023"]
                     and best["score_2024"] < trial0["score_2024"])
        settings = {k: best[k] for k in START} if adopt else dict(START)
        # Tweedie power for the mean model, on scaled squared error of the mean, with the chosen tree settings
        tw = []
        for pw in TWEEDIE:
            row = done(f"tweedie_{pw}", fset, half)
            if row is None or not all(np.isclose(float(row[k]), float(v)) for k, v in settings.items()):
                r = run_trial(d, settings, fset, threads, keep, tweedie=pw)
                row = dict(trial=f"tweedie_{pw}", feature_set=fset, half=half, **settings, **r); append_trial(row)
            tw.append(dict(power=pw, mean_sq_error=float(row["mean_sq_error"])))
        power = min(tw, key=lambda x: x["mean_sq_error"])["power"]
        json.dump({"settings": settings, "feature_set": fset, "tweedie_power": power, "adopted_tuned": adopt,
                   "best_trial": best["trial"], "gain_vs_start_pct": 100 * gain, "trials_run": n_trials, "half_series": half,
                   "trial_seconds": t_trial}, open(OUT / "chosen_config.json", "w"), indent=1)
        print(f"feature set {fset}; best trial {best['trial']} gain {100 * gain:+.2f}%; adopted {adopt}; tweedie {power}")
    elif mode == "run":
        st = load_settings(sys.argv[3]); fy0, fy1 = int(sys.argv[4]), int(sys.argv[5])
        RESUME = len(sys.argv) > 6 and sys.argv[6] == "resume"     # skip fit years whose file reads cleanly
        cfgf = OUT / "chosen_config.json"
        meta = json.load(open(cfgf)) if (sys.argv[3] == "chosen" and cfgf.exists()) else {"feature_set": "base", "tweedie_power": 1.3}
        fset, power = meta["feature_set"], meta["tweedie_power"]
        t_start = time.time(); nfit = fy1 - fy0 + 1
        progress(base, f"tree model: start, fits {fy0}..{fy1} ({fset}, tweedie {power})", 0, nfit)
        # rounds: chosen on 2023 targets in the fit through Dec 2022 (section 6a), then fixed for every fit, including
        # those that forecast 2025, 2026 and live months; no fit is ever stopped against 2025 or 2026 targets
        rf = OUT / "rounds_fixed.json"; first = None
        if rf.exists():
            rounds = {(int(k.split("_")[0][1:]), k.split("_", 1)[1]): v for k, v in json.load(open(rf)).items()}
        else:
            c22 = d.mi[pd.Period("2022-12", "M")]
            first = fit_models(d, c22, st, fset, threads, Q, rounds=None, valid_year=2023, tweedie=power)
            rounds = first[4]
            json.dump({f"h{h}_{n}": int(r) for (h, n), r in rounds.items()}, open(rf, "w"), indent=1)
            progress(base, f"tree model: rounds fixed on 2023 targets ({min(rounds.values())}-{max(rounds.values())})")
        for fy in range(fy0, fy1 + 1):
            cutoff = d.mi[pd.Period(f"{fy}-12", "M")] if pd.Period(f"{fy}-12", "M") in d.mi else d.M - 1
            t0 = time.time()
            fo = OUT / f"tree_fit{fy}.parquet"
            if fo.exists() and RESUME:
                try:
                    pd.read_parquet(fo, columns=["sid"]); progress(base, f"tree model: fit {fy} already done (resumed)"); continue
                except Exception:
                    fo.unlink(missing_ok=True)
            if fy == 2022 and first is not None:
                models, feats, sc, cats, _ = first           # the rounds fit already uses those rounds
                models = {k: m for k, m in models.items()}
            else:
                models, feats, sc, cats, _ = fit_models(d, cutoff, st, fset, threads, Q, rounds=rounds, tweedie=power)
            orig = [o for o in range(cutoff, min(cutoff + 12, d.M))]
            p = predict(d, models, feats, sc, cats, orig, fset).assign(member="tree")
            p.to_parquet(OUT / f"tree_fit{fy}.parquet", index=False)
            progress(base, f"tree model: fit {fy} done", fy - fy0 + 1, nfit, t_start)
            print(f"fit {fy}: {len(p):,} rows, origins {d.months[orig[0]]}..{d.months[orig[-1]]}, {time.time() - t0:.0f}s", flush=True)
    else:
        sys.exit(f"unknown mode {mode}")
