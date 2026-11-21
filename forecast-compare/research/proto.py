import math, time, json, sys
import numpy as np
import verify as V

def nelder_mead(f, x0, steps, max_iter, tol=1e-10):
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (steps[j] if j == i else 0.0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for it in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]; vals = [vals[i] for i in order]
        if abs(vals[n] - vals[0]) <= tol * (abs(vals[0]) + tol): break
        c = [sum(pts[i][j] for i in range(n)) / n for j in range(n)]
        xr = [c[j] + (c[j] - pts[n][j]) for j in range(n)]; fr = f(xr)
        if fr < vals[0]:
            xe = [c[j] + 2 * (c[j] - pts[n][j]) for j in range(n)]; fe = f(xe)
            if fe < fr: pts[n], vals[n] = xe, fe
            else: pts[n], vals[n] = xr, fr
        elif fr < vals[n - 1]:
            pts[n], vals[n] = xr, fr
        else:
            if fr < vals[n]:
                xc = [c[j] + 0.5 * (xr[j] - c[j]) for j in range(n)]; fc = f(xc)
                ok = fc <= fr
            else:
                xc = [c[j] + 0.5 * (pts[n][j] - c[j]) for j in range(n)]; fc = f(xc)
                ok = fc < vals[n]
            if ok: pts[n], vals[n] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]; vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: vals[i])
    return pts[i], vals[i]

BIG = 1e300
def hw_sse(y, m, p, out=False):
    a, b, g, l, tr = p[0], p[1], p[2], p[3], p[4]
    if not (0 < a < 1 and 0 < b < 1 and 0 < g < 1): return BIG
    s = list(p[5:5 + m]); sse = 0.0
    for t in range(len(y)):
        f = l + tr + s[t]
        e = y[t] - f; sse += e * e
        ln = a * (y[t] - s[t]) + (1 - a) * (l + tr)
        tr = b * (ln - l) + (1 - b) * tr
        s.append(g * (y[t] - l - (tr if False else 0) - 0) + (1 - g) * s[t]) if False else s.append(g * (y[t] - ln) + (1 - g) * s[t])
        l = ln
    if out: return l, tr, s
    return sse

def hw_opt(y, h, m, iters=3000):
    l0 = sum(y[:m]) / m; b0 = (sum(y[m:2*m]) / m - l0) / m
    s0 = [y[i] - (l0 + (i - (m - 1) / 2) * b0) for i in range(m)]
    x0 = [0.3, 0.1, 0.1, l0 - (m + 1) / 2 * b0, b0] + s0
    sc = (max(y) - min(y)) or 1.0
    steps = [0.1, 0.05, 0.05, 0.05 * sc, 0.01 * sc] + [0.05 * sc] * m
    x, v = nelder_mead(lambda p: hw_sse(y, m, p), x0, steps, iters)
    l, tr, s = hw_sse(y, m, x, out=True)
    T = len(y)
    return [l + k * tr + s[T + (k - 1) % m] for k in range(1, h + 1)]

def sarima_css(y, m, th, TH, out=False):
    if not (-1 < th < 1 and -1 < TH < 1): return BIG
    n = len(y); e = [0.0] * n; sse = 0.0
    for t in range(m + 1, n):
        w = y[t] - y[t-1] - y[t-m] + y[t-m-1]
        et = w - th * e[t-1] - TH * e[t-m] - th * TH * e[t-m-1]
        e[t] = et; sse += et * et
    return e if out else sse

def sarima(y, h, m):
    x, v = nelder_mead(lambda p: sarima_css(y, m, p[0], p[1]), [-0.3, -0.5], [0.2, 0.2], 500)
    th, TH = x; e = sarima_css(y, m, th, TH, out=True)
    yy = list(y); ee = list(e); n = len(y)
    for k in range(h):
        t = n + k
        w = th * ee[t-1] + TH * ee[t-m] + th * TH * ee[t-m-1]
        ee.append(0.0); yy.append(yy[t-1] + yy[t-m] - yy[t-m-1] + w)
    return yy[n:]

def comb(fns):
    def f(y, h, m): 
        fs = [fn(y, h, m) for fn in fns]; return [sum(c[k] for c in fs) / len(fs) for k in range(h)]
    return f

base = {k: (lambda fn: (lambda y, h, m: fn(y, h, m)[0]))(fn) for k, fn, s in V.METHODS}
cand = dict(base)
cand["hw_opt"] = hw_opt
cand["sarima"] = sarima
cand["comb_dhs"] = comb([base["damped"], hw_opt, sarima])
cand["comb_hs"] = comb([hw_opt, sarima])
cand["comb_shd"] = comb([base["ses"], base["holt"], base["damped"]])

FILES = ["SAMPLE_demand", "FRGSHPUSM649NCIS", "PCU322211322211", "PCOPPUSDM", "DJFUELUSGULF"]
M, H = 12, 12
res = {}
t0 = time.time()
for f in FILES:
    y = V.load("data/" + f + ".csv"); n = len(y)
    fc = {k: {T: fn(y[:T], H, M) for T in range(n - 36, n)} for k, fn in cand.items()}
    res[f] = {"y": y, "fc": {k: {str(T): v for T, v in d.items()} for k, d in fc.items()}}
    print(f, round(time.time() - t0, 1), file=sys.stderr)
json.dump(res, open("proto_fc.json", "w"))
