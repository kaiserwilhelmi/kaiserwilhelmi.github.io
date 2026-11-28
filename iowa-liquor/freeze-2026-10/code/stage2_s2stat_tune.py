"""Section 6a tuning of the intermittent-class members, per demand class (SBC intermittent and lumpy), on targets in
2023 and 2024 only (origins Dec 2022 - Nov 2024, horizons 1-3):
- SBA: size and interval smoothing, each from {0.05, 0.1, 0.2, 0.3}; TSB: size and probability, each from the same set;
  ADIDA: aggregation length from {2, 3, 4, 6}.
- Each member is scored on its own with the full selection metric within its class (7 negative-binomial quantiles in
  the recorded unit, scaled, weighted by trailing dollars, excl. open handover windows and the separately scored series;
  averaged over origins, then over horizons).
- Stop rule: a tuned value replaces the starting value (0.1 / 0.1, length 3) only if it lowers the member's score by 1% or
  more AND beats it in 2023 and in 2024 separately.
Writes stage2/stat_tune_results.csv (every setting's score) and stage2/stat_params.json.
Usage: python s2stat_tune.py <base> [workers]"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys, json, time, warnings, itertools
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import s2stat
from s2common import Data, Q, H, progress, scored_mask

A = (0.05, 0.1, 0.2, 0.3); N = (2, 3, 4, 6)
GRID = ([("sba", p) for p in itertools.product(A, A)] + [("tsb", p) for p in itertools.product(A, A)] +
        [("adida", (n,)) for n in N])
START = {"sba": (0.1, 0.1), "tsb": (0.1, 0.1), "adida": (3,)}
CLASSES = ("intermittent", "lumpy")
D = None


def _init(cache):
    global D
    import pickle
    warnings.filterwarnings("ignore")
    with open(cache, "rb") as f:
        D = pickle.load(f)


def run_origin(o):
    d = D; M = d.M
    eff = d.eff_days(o); Ypd = d.Y / eff[None, :M]
    pool, sbc = d.classes(o)
    k_o = d.K_rec[:, o]
    w = np.where((d.cols[None, :] > o - 24) & (d.cols[None, :] <= o), d.Y * d.K_rec, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mu = np.nanmean(w, axis=1); v = np.nanvar(w, axis=1, ddof=1)
    nzc = np.sum(w > 0, axis=1)
    size = np.where(v > mu, mu ** 2 / np.maximum(v - mu, 1e-12), np.inf)
    est = (nzc >= 6) & np.isfinite(mu)
    m_ = (pool == "intermittent")
    fin = m_ & est & np.isfinite(size)
    size = np.where(m_ & ~est, np.median(size[fin]) if fin.any() else np.inf, size)
    w12 = d.weight12(o)
    rows = []
    for h in H:
        t = o + h
        if t >= M or d.months[t].year not in (2023, 2024):
            continue
        _, ok, sc = scored_mask(d, o, t)
        for cl in CLASSES:
            S = np.flatnonzero(ok & m_ & (sbc == cl))
            if not len(S):
                continue
            y_t = np.nan_to_num(d.Y[S, t]); ww = w12[S]
            for mem, par in GRID:
                rate = np.empty(len(S))
                for i, s in enumerate(S):
                    yy = Ypd[s, d.first[s]:o + 1]
                    rate[i] = (s2stat.croston_sba(yy, *par) if mem == "sba" else s2stat.tsb(yy, *par) if mem == "tsb"
                               else s2stat.adida(yy, par[0]))
                mean = np.maximum(rate, 0) * eff[t]
                q = s2stat.nb_quantiles(mean * k_o[S], size[S]) / k_o[S][:, None]
                dd = y_t[:, None] - q
                L = np.where(dd >= 0, dd * Q, -dd * (1 - Q)).mean(1) / sc[S]
                rows.append(dict(o=o, h=h, year=d.months[t].year, cls=cl, member=mem, params=str(par),
                                 loss=float((ww * L).sum() / ww.sum())))
    return rows


if __name__ == "__main__":
    import multiprocessing as mp, pickle
    warnings.filterwarnings("ignore")
    base = Path(sys.argv[1]); workers = int(sys.argv[2]) if len(sys.argv) > 2 else max(1, (os.cpu_count() or 2) - 2)
    out = base / "stage2"
    D = Data(base)
    origins = [D.mi[p] for p in pd.period_range("2022-12", "2024-11", freq="M")]
    cache = out / "_tune_cache.pkl"
    with open(cache, "wb") as f:
        pickle.dump(D, f, protocol=pickle.HIGHEST_PROTOCOL)
    t0 = time.time(); rows = []
    progress(base, f"stat tuning: {len(origins)} origins, {len(GRID)} settings, {workers} workers", 0, len(origins))
    with mp.Pool(min(workers, len(origins)), initializer=_init, initargs=(str(cache),)) as pool:
        for i, r in enumerate(pool.imap_unordered(run_origin, origins), 1):
            rows += r
            progress(base, "stat tuning: origin done", i, len(origins), t0)
    cache.unlink(missing_ok=True)
    R = pd.DataFrame(rows)
    # per class, member and setting: mean over origins per horizon, then over horizons; and per year
    s = R.groupby(["cls", "member", "params", "h"]).loss.mean().groupby(level=[0, 1, 2]).mean().rename("score").to_frame()
    for y in (2023, 2024):
        s[f"score_{y}"] = R[R.year == y].groupby(["cls", "member", "params", "h"]).loss.mean().groupby(level=[0, 1, 2]).mean()
    s = s.reset_index()
    s.to_csv(out / "stat_tune_results.csv", index=False)
    params, report = {}, []
    for (cl, mem), g in s.groupby(["cls", "member"]):
        st = g[g.params == str(START[mem])].iloc[0]; best = g.loc[g.score.idxmin()]
        gain = 1 - best.score / st.score
        adopt = bool(best.params != st.params and gain >= 0.01 and best.score_2023 < st.score_2023 and best.score_2024 < st.score_2024)
        chosen = eval(best.params) if adopt else START[mem]
        params.setdefault(cl, {})[mem] = list(chosen) if mem != "adida" else int(chosen[0])
        report.append(dict(cls=cl, member=mem, start=str(START[mem]), best=best.params, gain_pct=100 * gain, adopted=adopt,
                           chosen=str(chosen)))
    rep = pd.DataFrame(report); rep.to_csv(out / "stat_tune_choices.csv", index=False)
    json.dump({"params": params, "note": "section 6a, 2023-24 targets only; stop rule 1% and both years"},
              open(out / "stat_params.json", "w"), indent=1)
    print(rep.to_string(index=False)); print(f"{time.time() - t0:.0f}s")
