import json, sys, numpy as np
d = json.load(open(sys.argv[1])); H = 6
def mase(s, mid, lo, hi):
    y, m = s["y"], s["m"]; n = len(y)
    sc = np.mean([abs(y[t]-y[t-m]) for t in range(m, n-36)])
    e = [abs(y[T+k-1] - s["fc"][mid][str(T)][k-1]) for T in range(lo, hi) for k in range(1, H+1) if T+k-1 < hi]
    return np.mean(e)/sc if sc > 0 else np.nan
meths = sorted({k for s in d for k in s["fc"]})
# (1) last 24 origins, all methods
tab = {mm: [] for mm in meths}
for s in d:
    n = len(s["y"])
    for mm in meths: tab[mm].append(mase(s, mm, n-24, n) if mm in s["fc"] else np.nan)
A = np.array([tab[mm] for mm in meths])
ranks = np.full(A.shape, np.nan)
for j in range(A.shape[1]):
    col = A[:, j]; ok = ~np.isnan(col); r = np.argsort(np.argsort(col[ok])) + 1; ranks[ok, j] = r
print(f"{len(d)} series, h={H}, last 24 origins. MASE: mean / median / mean rank / #wins")
wins = np.nanargmin(np.where(np.isnan(A), np.inf, A), axis=0)
for i in np.argsort(np.nanmean(A, axis=1)):
    print(f"  {meths[i]:8s} {np.nanmean(A[i]):.3f} {np.nanmedian(A[i]):.3f}  rank {np.nanmean(ranks[i]):5.2f}  wins {int(np.sum(wins==i))}")
# (2) nested selection: choose on origins n-36..n-13 (scored inside that window), evaluate on n-12..n
def nested(pool):
    res = []
    for s in d:
        n = len(s["y"]); P = [p for p in pool if p in s["fc"]]
        sel = min(P, key=lambda p: mase(s, p, n-36, n-12))
        res.append(mase(s, sel, n-12, n))
    return np.array(res)
cur = ["naive","snaive","drift","ma3","ses","holt","damped","hw","sarima","tslm","combS","combN"]
new = cur + ["theta","ridge","gbm","combS3","combN3","combML"] + (["mlp"] if "mlp" in meths else [])
stat = cur + ["theta","combS3","combN3"]
for lab, pool in [("current lineup", cur), ("+ Theta only", stat), ("+ Theta + ML", new)]:
    r = nested(pool); print(f"nested pick-by-backtest, {lab:16s}: mean MASE {np.nanmean(r):.3f}, median {np.nanmedian(r):.3f}")
for p in ["naive", "theta", "combS3"]:
    r = np.array([mase(s, p, len(s['y'])-12, len(s['y'])) if p in s["fc"] else np.nan for s in d]); print(f"always {p:8s}: mean {np.nanmean(r):.3f} median {np.nanmedian(r):.3f}")
from scipy.stats import wilcoxon
real = [s for s in d if not s["name"].startswith("test/") and s["name"] != "SAMPLE"]
print("--- real FRED series only:", len(real))
dd = d; d = real
a = nested(cur); b = nested(stat); c = nested(new)
for lab, r in [("current", a), ("+Theta", b), ("+Theta+ML", c)]: print(f"  {lab:10s} mean {np.mean(r):.3f} median {np.median(r):.3f}")
print("  Wilcoxon current vs +Theta+ML p =", wilcoxon(a, c).pvalue, "; better on", int(np.sum(c < a - 1e-12)), "worse on", int(np.sum(c > a + 1e-12)), "of", len(a))
print("  Wilcoxon current vs +Theta    p =", wilcoxon(a, b).pvalue)
# which methods get picked
from collections import Counter
cnt = Counter()
for s in real:
    n = len(s["y"]); cnt[min(new, key=lambda p: mase(s, p, n-36, n-12) if p in s["fc"] else 9e9)] += 1
print("  picked with full lineup:", dict(cnt))
