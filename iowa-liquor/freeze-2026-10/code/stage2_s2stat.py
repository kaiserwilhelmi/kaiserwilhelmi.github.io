"""Stage 2 statistical members (protocol 1.4 section 6), refitted at every origin. Output per series, origin, horizon
and member: mean and 7 quantiles in MONTHLY BOTTLES (per-order-day forecast x the target month's effective order days).
Members: seasonal naive (layer a), ETS (regular), SBA + TSB + ADIDA (intermittent and lumpy), own mean (new).
Usage: python s2stat.py <base> <first origin YYYY-MM> <last origin YYYY-MM> [workers]"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import os, sys, time, warnings
os.environ.setdefault("OMP_NUM_THREADS", "1"); os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q, H, FUTURE, progress

QC = [f"q{int(round(q * 100)):02d}" for q in Q]
ALPHA = 0.1          # SBA size and interval, TSB size and probability: starting value and fallback (section 6)
D = None
PARAMS = {}          # tuned per demand class by s2stat_tune.py (section 6a); loaded from stage2/stat_params.json if present


def load_params(base):
    global PARAMS
    f = Path(base) / "stage2" / "stat_params.json"
    if f.exists():
        import json
        PARAMS = {k: {m: (tuple(v) if isinstance(v, list) else v) for m, v in d.items()} for k, d in json.load(open(f))["params"].items()}
    return PARAMS


def _init(cache):
    """Workers read the parent's pickled data (no DuckDB in workers: 14 processes opening the database at once hung
    on Windows, Nov 27)."""
    global D
    import pickle
    warnings.filterwarnings("ignore")
    with open(cache, "rb") as f:
        D = pickle.load(f)
    load_params(D.base)


def snaive(X, first, o, h, M):
    S = X.shape[0]
    age = o - first + 1
    hist = np.where(np.arange(M)[None, :] <= o, X, np.nan)
    pt_old = X[:, o + h - 12]
    lag = np.concatenate([np.full((S, 12), np.nan), hist[:, :-12]], axis=1)
    e_old = hist - lag
    e_old[:, :max(o - 35, 0)] = np.nan
    with np.errstate(all="ignore"):
        mean_young = np.nanmean(hist, axis=1)
    e_young = hist - mean_young[:, None]
    old = age >= 13
    pt = np.where(old, pt_old, mean_young)
    E = np.where(old[:, None], e_old, e_young)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eq = np.nanquantile(E, Q, axis=1).T
    return pt, np.sort(np.maximum(pt[:, None] + np.nan_to_num(eq), 0), axis=1)


def ets_one(y, h_max=3):
    """y: bottles per order day from the first order month to the origin. Returns (means[3], sds[3], form)."""
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
    y = pd.Series(np.asarray(y, float))
    forms = [("level", dict(trend=None, seasonal=None)), ("damped", dict(trend="add", damped_trend=True, seasonal=None))]
    if len(y) >= 36:
        forms += [("level+season", dict(trend=None, seasonal="add", seasonal_periods=12)),
                  ("damped+season", dict(trend="add", damped_trend=True, seasonal="add", seasonal_periods=12))]
    best = None
    for name, kw in forms:
        try:
            r = ETSModel(y, error="add", **kw).fit(disp=False)
            if np.isfinite(r.aicc) and (best is None or r.aicc < best[0]):
                best = (r.aicc, r, name)
        except Exception:
            continue
    if best is None:
        return np.repeat(y.mean(), h_max), np.repeat(y.std(ddof=1) if len(y) > 1 else 0.0, h_max), "fallback mean"
    p = best[1].get_prediction(start=len(y), end=len(y) + h_max - 1)
    return np.asarray(p.predicted_mean), np.sqrt(np.maximum(np.asarray(p.var_pred_mean), 0)), best[2]


def croston_sba(y, a_size=ALPHA, a_int=ALPHA):
    z = p = None; q = 1
    for v in y:
        if v > 0:
            if z is None:
                z, p = v, q
            else:
                z += a_size * (v - z); p += a_int * (q - p)
            q = 1
        else:
            q += 1
    return 0.0 if z is None else (1 - a_int / 2) * z / p


def tsb(y, a_size=ALPHA, a_prob=ALPHA):
    nzv = y[y > 0]
    if len(nzv) == 0:
        return 0.0
    z = nzv[0]; pr = float(np.mean(y > 0))
    for v in y:
        pr += a_prob * ((v > 0) - pr)
        if v > 0:
            z += a_size * (v - z)
    return pr * z


def adida(y, n=3):
    k = len(y) // n
    if k == 0:
        return float(np.mean(y)) if len(y) else 0.0
    b = y[len(y) - n * k:].reshape(k, n).sum(1)     # non-overlapping n-month totals ending at the origin
    if k == 1:
        return b[0] / n
    best = None
    for a in np.round(np.arange(0.05, 0.501, 0.01), 2):
        lev = b[0]; sse = 0.0
        for v in b[1:]:
            sse += (v - lev) ** 2; lev += a * (v - lev)
        if best is None or sse < best[0]:
            best = (sse, lev)
    return best[1] / n


def nb_quantiles(m, size):
    """m: monthly mean (array), size: NB size r (np.inf -> Poisson)."""
    m = np.maximum(m, 1e-9)
    out = np.empty((len(m), len(Q)))
    pois = ~np.isfinite(size)
    if pois.any():
        out[pois] = stats.poisson.ppf(Q[None, :], m[pois, None])
    if (~pois).any():
        r = size[~pois]; pp = r / (r + m[~pois])
        out[~pois] = stats.nbinom.ppf(Q[None, :], r[:, None], pp[:, None])
    return out


def run_origin(o):
    t0 = time.time()
    d = D; M = d.M
    eff = d.eff_days(o)
    Ypd = d.Y / eff[None, :d.M]
    pool, sbc = d.classes(o)
    act = pool != ""
    rows = []
    # (a) seasonal naive, all active series
    for h in H:
        t = o + h
        if t >= M + FUTURE:
            continue
        _, q = snaive(Ypd, d.first, o, h, M)
        pt, _ = snaive(Ypd, d.first, o, h, M)
        for s in np.flatnonzero(act):
            rows.append((s, o, h, "seasonal_naive", pt[s] * eff[t], *(q[s] * eff[t])))
    # dispersion for the NB members: monthly bottles over the last 24 months at the origin, in the state's RECORDED
    # unit (decision 50: restated units are fractional, so count quantiles are computed in recorded units and converted
    # back with the unit in force at the origin, k_o = recorded / restated)
    k_o = d.K_rec[:, o]
    w = np.where((d.cols[None, :] > o - 24) & (d.cols[None, :] <= o), d.Y * d.K_rec, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mu = np.nanmean(w, axis=1); v = np.nanvar(w, axis=1, ddof=1)
    nzc = np.sum(w > 0, axis=1)
    size = np.where(v > mu, mu ** 2 / np.maximum(v - mu, 1e-12), np.inf)
    est = (nzc >= 6) & np.isfinite(mu)
    for cl in ("intermittent", "new"):
        m_ = act & (pool == cl)
        fin = m_ & est & np.isfinite(size)
        med = np.median(size[fin]) if fin.any() else np.inf
        size = np.where(m_ & ~est, med, size)
    n_fail = 0
    todo_s = np.flatnonzero(act)
    for k_, s in enumerate(todo_s):
        if k_ and k_ % 3000 == 0:
            progress(d.base, f"stat members: origin {d.months[o]}, series {k_:,} of {len(todo_s):,} ({time.time() - t0:.0f}s)")
        y = Ypd[s, d.first[s]:o + 1]
        cl = pool[s]
        if cl == "regular":
            mean, sd, form = ets_one(y)
            if form == "fallback mean":
                n_fail += 1
            for i, h in enumerate(H):
                t = o + h
                if t >= M + FUTURE:
                    continue
                q = np.maximum(mean[i] + sd[i] * stats.norm.ppf(Q), 0)
                rows.append((s, o, h, "ets", max(mean[i], 0) * eff[t], *(q * eff[t])))
        else:
            pp = PARAMS.get(sbc[s], {})          # section 6a: per demand class (intermittent / lumpy); defaults otherwise
            members = ({"sba": croston_sba(y, *pp.get("sba", (ALPHA, ALPHA))), "tsb": tsb(y, *pp.get("tsb", (ALPHA, ALPHA))),
                        "adida": adida(y, pp.get("adida", 3))} if cl == "intermittent"
                       else {"own_mean": float(np.mean(y))})
            for name, rate in members.items():
                for h in H:
                    t = o + h
                    if t >= M + FUTURE:
                        continue
                    m = np.array([max(rate, 0) * eff[t]])
                    q = nb_quantiles(m * k_o[s], np.array([size[s]]))[0] / k_o[s]     # recorded unit, then back
                    rows.append((s, o, h, name, m[0], *q))
    df = pd.DataFrame(rows, columns=["sid", "o", "h", "member", "mean", *QC])
    df["pool_class"] = pool[df.sid]; df["sbc_class"] = sbc[df.sid]
    return df, dict(o=str(d.months[o]), series=int(act.sum()), ets_fallbacks=n_fail, seconds=round(time.time() - t0, 1),
                    **{f"n_{k}": int((pool == k).sum()) for k in ("regular", "intermittent", "new")})


if __name__ == "__main__":
    import multiprocessing as mp
    base = Path(sys.argv[1]); o0, o1 = sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else max(1, (os.cpu_count() or 2) - 2)
    out = base / "stage2" / "members"; out.mkdir(parents=True, exist_ok=True)
    import pickle
    progress(base, "stat members: loading data")
    D = Data(base)
    load_params(base)
    if PARAMS:
        progress(base, f"stat members: tuned class parameters {PARAMS}")
    cache = out / "_data_cache.pkl"
    with open(cache, "wb") as f:
        pickle.dump(D, f, protocol=pickle.HIGHEST_PROTOCOL)
    progress(base, f"stat members: data loaded, {D.S:,} series")
    origins = [D.mi[p] for p in pd.period_range(o0, o1, freq="M")]
    # resume (ruling-02-resume item 2): skip origins whose file exists and reads cleanly; delete and redo unreadable ones
    def _ok(o):
        f = out / f"members_{D.months[o]}.parquet"
        if not f.exists():
            return False
        try:
            pd.read_parquet(f, columns=["sid"]); return True
        except Exception:
            f.unlink(missing_ok=True); progress(base, f"stat members: {f.name} unreadable, deleted and redone"); return False
    todo = [o for o in origins if not _ok(o)]
    print(f"{len(origins)} origins, {len(todo)} to run, {workers} workers", flush=True)
    import time; t_start = time.time()
    progress(base, f"stat members: start, {len(todo)} origins {o0}..{o1}, {workers} workers", 0, len(todo))
    logs = []
    def _save(df, log):
        df.to_parquet(out / f"members_{log['o']}.parquet", index=False)
        logs.append(log); print(log, flush=True)
        progress(base, f"stat members: origin {log['o']} done", len(logs), len(todo), t_start)
    if workers == 1 or len(todo) == 1:          # in-process, no pool
        for o in todo:
            _save(*run_origin(o))
    else:
        with mp.Pool(min(workers, len(todo)), initializer=_init, initargs=(str(cache),)) as pool:
            for df, log in pool.imap_unordered(run_origin, todo):
                _save(df, log)
    cache.unlink(missing_ok=True)
    if logs:
        pd.DataFrame(logs).sort_values("o").to_csv(base / "stage2" / "members_log.csv", index=False)
