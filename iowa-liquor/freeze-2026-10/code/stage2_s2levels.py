"""Protocol 1.10 section 2: brand, category and state levels.
- The number that adds up (headline) is the bottom-up sum of product means; in dollars (decision 52: units are never
  summed above the product), product mean units x average price paid per unit as of the origin.
- Ranges: each level's monthly dollars are also forecast directly with seasonal exponential smoothing (section 6 settings:
  additive-error ETS on dollars per effective order day, form by AICc, seasonal forms only with 36+ months), calibrated
  in time order per level type and horizon (section 8: split conformal on scaled errors over the 12 most recent observed
  target months; a calibration set needs 19 errors, so the state uses a 36-month window, and categories do too if they have
  fewer than 19). Ranges are not forced to add up.
- If the bottom-up sum falls outside the level's own direct 50% range, both are shown and the row is flagged.
- Brands: named brands only where at least 95% of trailing-12 dollars sit on hand-checked series (decision 49); other
  brands are summed over their hand-checked series only and labelled so. Brands with no hand-checked series get no row.
Scores are not computed here (levels are reported beside the product metric, never used to choose).
Usage: python s2levels.py <base> <first origin> <last origin> [workers]   ->  stage2/levels_forecasts.parquet"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, str(Path(__file__).parent))
import s2stat
from s2common import Data, Q, H, progress

QC = [f"q{int(round(q * 100)):02d}" for q in Q]


def level_matrix(d, base):
    """rows = levels (state, categories, brands); columns = months; values = dollars; plus membership."""
    bm = pd.read_csv(base / "stage2" / "brand_map.csv", dtype={"series_id": str})
    hs = bm.assign(h=bm.brand_source == "hand-checked").groupby("brand").apply(
        lambda g: (g.d12 * g.h).sum() / g.d12.sum() if g.d12.sum() > 0 else 0, include_groups=False)
    sid_pos = {s: i for i, s in enumerate(d.sids)}
    levels = [("state", "Iowa", np.arange(d.S), "")]
    for c in sorted(set(d.category)):
        levels.append(("category", c, np.flatnonzero(d.category == c), ""))
    for b, share in hs.items():
        g = bm[bm.brand == b]
        if share >= 0.95:
            members, label = g.series_id, ""
        else:
            members, label = g[g.brand_source == "hand-checked"].series_id, "hand-checked products only"
        idx = np.array([sid_pos[s] for s in members if s in sid_pos], dtype=int)
        if len(idx) and (g.brand_source == "hand-checked").any():
            levels.append(("brand", b, idx, label))
    X = np.vstack([np.nansum(d.D[i], axis=0) for _, _, i, _ in levels])
    return levels, X


def direct(Xpd, first, o, eff):
    rows = []
    for k in range(Xpd.shape[0]):
        y = Xpd[k, first[k]:o + 1]
        if len(y) < 13 or not np.isfinite(y).all():
            continue
        mean, sd, form = s2stat.ets_one(y)
        for i, h in enumerate(H):
            q = np.maximum(mean[i] + sd[i] * stats.norm.ppf(Q), 0) * eff[o + h]
            rows.append((k, o, h, max(mean[i], 0) * eff[o + h], *q))
    return rows


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    base = Path(sys.argv[1]); o0, o1 = sys.argv[2], sys.argv[3]
    d = Data(base)
    levels, X = level_matrix(d, base)
    first = np.argmax(X > 0, axis=1)
    origins = [d.mi[p] for p in pd.period_range(o0, o1, freq="M")]
    progress(base, f"levels: {len(levels)} levels ({sum(l[0] == 'brand' for l in levels)} brands), {len(origins)} origins")
    rows = []
    for j, o in enumerate(origins, 1):
        eff = d.eff_days(o)
        rows += direct(X / eff[None, :d.M], first, o, eff)
        progress(base, "levels: origin done", j, len(origins))
    F = pd.DataFrame(rows, columns=["k", "o", "h", "mean", *QC])
    F["level"] = [levels[k][0] for k in F.k]; F["name"] = [levels[k][1] for k in F.k]; F["label"] = [levels[k][3] for k in F.k]
    # calibration in time order per level type and horizon, on scaled errors (scale: mean abs month-to-month change)
    with np.errstate(all="ignore"):
        scale = {o: np.nanmean(np.abs(np.diff(np.where(d.cols[None, :] <= o, X, np.nan), axis=1)), axis=1) for o in origins}
    F["s"] = [scale[o][k] for k, o in zip(F.k, F.o)]
    F["t"] = F.o + F.h
    F["y"] = [X[k, t] if t < d.M else np.nan for k, t in zip(F.k, F.t)]
    R = F[F.y.notna() & (F.s > 0)].copy()
    for c in QC:
        R[c + "_e"] = (R.y - R[c]) / R.s
    out = []
    for (o, h, lv), g in F.groupby(["o", "h", "level"]):
        g = g.copy()
        win = 36 if lv == "state" else 12
        r = R[(R.h == h) & (R.level == lv) & (R.t <= o) & (R.t > o - win)]
        if lv == "category" and len(r) < 19:
            r = R[(R.h == h) & (R.level == lv) & (R.t <= o) & (R.t > o - 36)]
        if len(r) >= 19:
            adj = np.array([np.quantile(r[c + "_e"], q) for c, q in zip(QC, Q)])
            g[QC] = np.sort(np.maximum(g[QC].to_numpy() + adj[None, :] * g.s.to_numpy()[:, None], 0), axis=1)
            g["calibrated"] = True
        else:
            g["calibrated"] = False
        out.append(g)
    F = pd.concat(out).drop(columns=["y"])
    # bottom-up headline from the chosen product layer: units mean x price per unit as of the origin
    chosen = json.load(open(base / "stage2" / "chosen_layer.json"))["chosen_layer"]
    Lp = pd.read_parquet(base / "stage2" / "layers.parquet", columns=["sid", "o", "h", "layer", "mean"])
    Lp = Lp[(Lp.layer == chosen) & Lp.o.isin(origins)]
    from s2tree import price_asof
    bu = []
    for o, g in Lp.groupby("o"):
        pr = price_asof(d, o); usd = np.zeros((d.S, 3))
        usd[g.sid.to_numpy(), g.h.to_numpy() - 1] = np.nan_to_num(g["mean"].to_numpy() * pr[g.sid.to_numpy()])
        for k, (_, _, idx, _) in enumerate(levels):
            for h in H:
                bu.append((k, o, h, usd[idx, h - 1].sum()))
    B = pd.DataFrame(bu, columns=["k", "o", "h", "bottom_up_dollars"])
    F = F.merge(B, on=["k", "o", "h"], how="left")
    F["outside_own_50"] = (F.bottom_up_dollars < F.q25) | (F.bottom_up_dollars > F.q75)
    F["layer_for_bottom_up"] = chosen
    F.drop(columns=["k"]).to_parquet(base / "stage2" / "levels_forecasts.parquet", index=False)
    last = F[F.o == origins[-1]]
    print(f"levels: {F.name.nunique()} levels, {len(origins)} origins; calibrated rows {F.calibrated.mean():.0%}; "
          f"last origin: bottom-up outside own 50% range in {int(last.outside_own_50.sum())} of {len(last)} level-horizons")
