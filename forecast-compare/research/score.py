import json, numpy as np
d = json.load(open("proto_fc.json")); M = 12
def mase(y, fc, test, h):
    n = len(y); first = n - test
    sc = np.mean([abs(y[t]-y[t-M]) for t in range(M, first)])
    e = [abs(y[T+k-1]-fc[str(T)][k-1]) for T in range(first, n) for k in range(1, h+1) if T+k-1 < n]
    return np.mean(e)/sc
methods = list(next(iter(d.values()))["fc"].keys())
for test in (24,):
  for h in (1, 6, 12):
    print(f"--- test={test} h={h}  (MASE per series; avg; avg rank)")
    tab = {m: [mase(v["y"], v["fc"][m], test, h) for v in d.values()] for m in methods}
    ranks = np.argsort(np.argsort(np.array([tab[m] for m in methods]), axis=0), axis=0) + 1
    for i, m in sorted(enumerate(methods), key=lambda x: np.mean(tab[x[1]])):
        print(f"{m:10s}", " ".join(f"{x:6.3f}" for x in tab[m]), f"| avg {np.mean(tab[m]):.3f} rank {ranks[i].mean():.1f}")
# selection experiment: pick by backtest over 24 months ending 12 months before end, score on last 12 (h=6)
print("--- pick-by-backtest (24m window, older) then score on newest 12m, h=6")
for name, v in d.items():
    y = v["y"]; n = len(y)
    def sub(fc, lo, hi, h=6):
        sc = np.mean([abs(y[t]-y[t-M]) for t in range(M, n-36)])
        return np.mean([abs(y[T+k-1]-fc[str(T)][k-1]) for T in range(lo, hi) for k in range(1,h+1) if T+k-1 < hi])/sc
    sel = {m: sub(v["fc"][m], n-36, n-12) for m in methods}
    pick = min(sel, key=sel.get)
    out = {m: sub(v["fc"][m], n-12, n) for m in methods}
    best = min(out, key=out.get)
    print(f"{name:18s} picked {pick:9s} -> {out[pick]:.3f} | comb_dhs {out['comb_dhs']:.3f} | naive {out['naive']:.3f} | hindsight best {best} {out[best]:.3f}")
