import json, sys, numpy as np
from scipy import stats
d = json.load(open(sys.argv[1])); H = 6
ORDER = ["naive","snaive","drift","ses","ma3","theta","holt","damped","tslm","hw","sarima","combN","combS","combN3","combS3","ridge","gbm","mlp","combML"]
def losses(s, mid, lo, hi):  # per-origin mean absolute error (scaled)
    y, m = s["y"], s["m"]; n = len(y); sc = np.mean([abs(y[t]-y[t-m]) for t in range(m, n-36)])
    return np.array([np.mean([abs(y[T+k-1]-s["fc"][mid][str(T)][k-1]) for k in range(1, H+1) if T+k-1 < hi])/sc for T in range(lo, hi)])
def dm_p(l1, l2, h=H):  # Diebold-Mariano with Harvey-Leybourne-Newbold correction, autocovariances up to h-1
    dlt = l1 - l2; T = len(dlt); mu = dlt.mean(); g = [np.mean((dlt[k:]-mu)*(dlt[:T-k]-mu)) for k in range(h)]
    v = (g[0] + 2*sum(g[1:])) / T
    if v <= 0: v = g[0] / T
    stat = mu / np.sqrt(v) * np.sqrt((T + 1 - 2*h + h*(h-1)/T) / T)
    return 2 * stats.t.sf(abs(stat), T - 1)
real = [s for s in d if not s["name"].startswith("test/") and s["name"] != "SAMPLE"]
for label, ds in [("real FRED", real), ("all incl. synthetic", d)]:
    r_best, r_rule, r_cur = [], [], []
    for s in ds:
        n = len(s["y"]); pool = [p for p in ORDER if p in s["fc"]]
        cur = [p for p in pool if p in ("naive","snaive","drift","ma3","ses","holt","damped","hw","sarima","tslm","combS","combN")]
        sel = {p: losses(s, p, n-36, n-12) for p in pool}
        best = min(pool, key=lambda p: sel[p].mean())
        # simplest method not significantly worse than the best (p >= 0.05)
        rule = next(p for p in pool if p == best or dm_p(sel[p], sel[best]) >= 0.05)
        cbest = min(cur, key=lambda p: sel[p].mean())
        ev = lambda p: losses(s, p, n-12, n).mean()
        r_best.append(ev(best)); r_rule.append(ev(rule)); r_cur.append(ev(cbest))
    r_best, r_rule, r_cur = map(np.array, (r_best, r_rule, r_cur))
    print(label, len(ds))
    for lab, r in [("current lineup, lowest error", r_cur), ("full lineup, lowest error", r_best), ("full lineup, simplest not sig. worse", r_rule)]:
        print(f"  {lab:38s} mean {r.mean():.3f} median {np.median(r):.3f}")
    print("  Wilcoxon cur vs rule p=%.3f  cur vs best p=%.3f" % (stats.wilcoxon(r_cur, r_rule).pvalue, stats.wilcoxon(r_cur, r_best).pvalue))
