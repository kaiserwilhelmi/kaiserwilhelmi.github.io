"""Independent Python re-implementation of every method and metric.

Runs the same rolling-origin backtest as engine.js and compares each metric, the
winner at each backtest window (stability check),
each MAE-by-horizon value, each future forecast and each fitted parameter
against the JS output (js_results.json, written by `node dump_js.js`).
Regression uses numpy least squares (a different solver from the JS
Gaussian elimination) as an extra independent check.
"""
import csv, json, math, sys
import numpy as np


def psum(xs):
    """Plain left-to-right float sum. Python 3.12+ built-in sum() uses compensated
    summation, which JavaScript does not, so the optimiser paths would drift apart."""
    s = 0.0
    for x in xs: s += x
    return s

GRID = [(2 * i + 1) / 20 for i in range(10)]
PHI = [0.8, 0.85, 0.9, 0.95, 0.98]


def naive(y, h, m): return [y[-1]] * h, None
def snaive(y, h, m): return [y[len(y) - m + (k - 1) % m] for k in range(1, h + 1)], None
def drift(y, h, m):
    s = (y[-1] - y[0]) / (len(y) - 1)
    return [y[-1] + k * s for k in range(1, h + 1)], None
def ma3(y, h, m): return [(y[-1] + y[-2] + y[-3]) / 3] * h, None


def ses(y, h, m):
    best = None
    for a in GRID:
        l, sse = y[0], 0.0
        for t in range(1, len(y)):
            e = y[t] - l; sse += e * e; l += a * e
        if best is None or sse < best[0]: best = (sse, l, a)
    return [best[1]] * h, {"alpha": best[2]}


def _holt(y, h, phis):
    best = None
    for phi in phis:
        for a in GRID:
            for b in GRID:
                l, tr, sse = y[0], y[1] - y[0], 0.0
                for t in range(1, len(y)):
                    f = l + phi * tr; e = y[t] - f; sse += e * e
                    ln = a * y[t] + (1 - a) * (l + phi * tr)
                    tr = b * (ln - l) + (1 - b) * phi * tr
                    l = ln
                if best is None or sse < best[0]: best = (sse, l, tr, a, b, phi)
    _, l, tr, a, b, phi = best
    out = [l + sum(phi ** j for j in range(1, k + 1)) * tr for k in range(1, h + 1)]
    return out, {"alpha": a, "beta": b, "phi": phi}


def holt(y, h, m):
    f, p = _holt(y, h, [1.0]); p.pop("phi"); return f, p
def damped(y, h, m): return _holt(y, h, PHI)


def nelder_mead(f, x0, steps, max_iter, tol=1e-10):
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (steps[j] if j == i else 0.0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for it in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]; vals = [vals[i] for i in order]
        if abs(vals[n] - vals[0]) <= tol * (abs(vals[0]) + tol): break
        c = [psum(pts[i][j] for i in range(n)) / n for j in range(n)]
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


def hw_run(y, m, p, keep=False):
    a, b, g, l, tr = p[0], p[1], p[2], p[3], p[4]
    if not (0 < a < 1 and 0 < b < 1 and 0 < g < 1): return BIG
    s = list(p[5:5 + m]); sse = 0.0
    for t in range(len(y)):
        e = y[t] - (l + tr + s[t]); sse += e * e
        ln = a * (y[t] - s[t]) + (1 - a) * (l + tr)
        tr = b * (ln - l) + (1 - b) * tr
        s.append(g * (y[t] - ln) + (1 - g) * s[t])
        l = ln
    return (l, tr, s) if keep else sse


def hw(y, h, m):
    l0 = psum(y[:m]) / m; b0 = (psum(y[m:2 * m]) / m - l0) / m
    x0 = [0.3, 0.1, 0.1, l0 - (m + 1) / 2 * b0, b0] + [y[i] - (l0 + (i - (m - 1) / 2) * b0) for i in range(m)]
    sc = (max(y) - min(y)) or 1.0
    steps = [0.1, 0.05, 0.05, 0.05 * sc, 0.01 * sc] + [0.05 * sc] * m
    x, _ = nelder_mead(lambda p: hw_run(y, m, p), x0, steps, 3000)
    l, tr, s = hw_run(y, m, x, keep=True); T = len(y)
    return [l + k * tr + s[T + (k - 1) % m] for k in range(1, h + 1)], {"alpha": x[0], "beta": x[1], "gamma": x[2]}


def sarima_run(y, m, th, TH, keep=False):
    if not (-1 < th < 1 and -1 < TH < 1): return BIG
    n = len(y); e = [0.0] * n; sse = 0.0
    for t in range(m + 1, n):
        w = y[t] - y[t - 1] - y[t - m] + y[t - m - 1]
        e[t] = w - th * e[t - 1] - TH * e[t - m] - th * TH * e[t - m - 1]; sse += e[t] * e[t]
    return e if keep else sse


def sarima(y, h, m):
    x, _ = nelder_mead(lambda p: sarima_run(y, m, p[0], p[1]), [-0.3, -0.5], [0.2, 0.2], 500)
    th, TH = x; e = sarima_run(y, m, th, TH, keep=True); yy = list(y); n = len(y)
    for k in range(h):
        t = n + k; w = th * e[t - 1] + TH * e[t - m] + th * TH * e[t - m - 1]
        e.append(0.0); yy.append(yy[t - 1] + yy[t - m] - yy[t - m - 1] + w)
    return yy[n:], {"theta": th, "Theta": TH}


# ---- Theta, ridge, boosted trees (independent re-implementation of engine.js) ----
def acf(y, k):
    mu = psum(y) / len(y); num = den = 0.0
    for t in range(len(y)):
        den += (y[t] - mu) * (y[t] - mu)
        if t >= k: num += (y[t] - mu) * (y[t - k] - mu)
    return 0.0 if den == 0 else num / den


def seasonal_test(y, m):
    if m <= 1 or len(y) < 3 * m: return False
    s = 0.0
    for k in range(1, m): r = acf(y, k); s += r * r
    return abs(acf(y, m)) > 1.645 * math.sqrt((1 + 2 * s) / len(y))


def seasonal_index(y, m, mult):
    n = len(y); half = m // 2; sums = [0.0] * m; cnt = [0] * m
    for t in range(half, n - half):
        s = 0.0
        for j in range(-half, half + 1):
            s += (0.5 if (m % 2 == 0 and j in (-half, half)) else 1.0) * y[t + j]
        s /= m
        sums[t % m] += y[t] / s if mult else y[t] - s; cnt[t % m] += 1
    idx = [sums[i] / cnt[i] for i in range(m)]; c = psum(idx) / m
    return [x / c if mult else x - c for x in idx]


def theta(y, h, m):
    n = len(y); seas = seasonal_test(y, m); mult = all(v > 0 for v in y)
    idx = seasonal_index(y, m, mult) if seas else None
    x = [(v / idx[i % m] if mult else v - idx[i % m]) for i, v in enumerate(y)] if seas else list(y)
    tm = (n - 1) / 2; xm = psum(x) / n; sxy = sxx = 0.0
    for t in range(n): sxy += (t - tm) * (x[t] - xm); sxx += (t - tm) * (t - tm)
    b0 = sxy / sxx; best = None
    for i in range(1, 100):
        a = i / 100; l = x[0]; sse = 0.0
        for t in range(1, n): e = x[t] - l; sse += e * e; l += a * e
        if best is None or sse < best[0]: best = (sse, l, a)
    _, l, a = best; decay = (1 - a) ** n; out = []
    for k in range(1, h + 1):
        v = l + 0.5 * b0 * ((1 - decay) / a + k - 1)
        if seas: v = v * idx[(n + k - 1) % m] if mult else v + idx[(n + k - 1) % m]
        out.append(v)
    return out, {"alpha": a}


def lags_for(m):
    p = min(m, 13) if m > 1 else 6
    return list(range(1, p + 1)) + ([m] if m > 13 else [])


def ml_design(y, m):
    d = [y[t] - y[t - 1] for t in range(1, len(y))]; L = lags_for(m); maxL = L[-1]
    sd = math.sqrt(psum(v * v for v in d) / len(d)) or 1.0
    z = [v / sd for v in d]
    X = [[z[t - l] for l in L] for t in range(maxL, len(z))]; Y = [z[t] for t in range(maxL, len(z))]
    return z, X, Y, L, sd


def ml_forecast(y, h, z, L, sd, predict):
    z = list(z); last = y[-1]; out = []
    for _ in range(h):
        dz = predict([z[len(z) - l] for l in L]); z.append(dz); last += dz * sd; out.append(last)
    return out


def gauss_solve(A, b):
    n = len(b); M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = c
        for r in range(c + 1, n):
            if abs(M[r][c]) > abs(M[p][c]): p = r
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1): M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for j in range(i + 1, n): s -= M[i][j] * x[j]
        x[i] = s / M[i][i]
    return x


def ridge_fit(X, Y, lam):
    p = len(X[0]) + 1; A = [[0.0] * p for _ in range(p)]; b = [0.0] * p
    for i in range(len(X)):
        x = [1.0] + X[i]
        for a in range(p):
            b[a] += x[a] * Y[i]
            for c in range(p): A[a][c] += x[a] * x[c]
    for a in range(1, p): A[a][a] += lam
    return gauss_solve(A, b)


def ridge_pred(w, x):
    s = w[0]
    for j in range(len(x)): s += w[j + 1] * x[j]
    return s


def ridge(y, h, m):
    z, X, Y, L, sd = ml_design(y, m); N = len(X)
    if N < 10: return naive(y, h, m)
    nv = max(4, N // 5); bestL, bestE = 1, None
    for lam in (0.1, 1, 10, 100):
        w = ridge_fit(X[:N - nv], Y[:N - nv], lam); e = 0.0
        for i in range(N - nv, N): r = ridge_pred(w, X[i]) - Y[i]; e += r * r
        if bestE is None or e < bestE: bestE, bestL = e, lam
    w = ridge_fit(X, Y, bestL)
    return ml_forecast(y, h, z, L, sd, lambda x: ridge_pred(w, x)), {"lambda": bestL}


def tree_eval(tr, x):
    kd = tr["kids"][0 if x[tr["j"]] <= tr["thr"] else 1]
    if "v" in kd: return kd["v"]
    return kd["l"] if x[kd["j"]] <= kd["thr"] else kd["r"]


def gbm(y, h, m):
    z, X, Y, L, sd = ml_design(y, m); n = len(X)
    if n < 10: return naive(y, h, m)
    p = len(X[0]); T = 150; lr = 0.05; min_leaf = max(3, n // 20)
    base = psum(Y) / n; pred = [base] * n; trees = []
    order = [sorted(range(n), key=lambda i, j=j: (X[i][j], i)) for j in range(p)]
    def split(sset, r):
        best = None; ins = set(sset); tot = 0.0; N = len(sset)
        for q in sset: tot += r[q]
        for j in range(p):
            ordj = [i for i in order[j] if i in ins]; sl = 0.0; nl = 0
            for k in range(len(ordj) - 1):
                sl += r[ordj[k]]; nl += 1
                if nl < min_leaf or N - nl < min_leaf: continue
                if X[ordj[k]][j] == X[ordj[k + 1]][j]: continue
                gain = sl * sl / nl + (tot - sl) * (tot - sl) / (N - nl)
                if best is None or gain > best[0]: best = (gain, j, (X[ordj[k]][j] + X[ordj[k + 1]][j]) / 2)
        return best
    def leaf(sset, r):
        if not sset: return 0.0
        s = 0.0
        for q in sset: s += r[q]
        return s / len(sset)
    allr = list(range(n))
    for _ in range(T):
        r = [Y[q] - pred[q] for q in range(n)]; s0 = split(allr, r)
        if s0 is None: break
        _, j0, t0 = s0
        kids = []
        for sset in ([q for q in allr if X[q][j0] <= t0], [q for q in allr if X[q][j0] > t0]):
            s = split(sset, r)
            if s is None: kids.append({"v": leaf(sset, r)})
            else:
                _, j1, t1 = s
                kids.append({"j": j1, "thr": t1, "l": leaf([q for q in sset if X[q][j1] <= t1], r), "r": leaf([q for q in sset if X[q][j1] > t1], r)})
        tree = {"j": j0, "thr": t0, "kids": kids}; trees.append(tree)
        for i in range(n): pred[i] += lr * tree_eval(tree, X[i])
    def predict(x):
        s = base
        for tr in trees: s += lr * tree_eval(tr, x)
        return s
    return ml_forecast(y, h, z, L, sd, predict), {"trees": len(trees)}


def dm_test(l1, l2, h):
    from scipy import stats
    T = len(l1); d = [a - b for a, b in zip(l1, l2)]; mu = psum(d) / T
    hh = max(1, min(h, (T - 1) // 2))
    g = [psum((d[i] - mu) * (d[i - k] - mu) for i in range(k, T)) / T for k in range(hh)]
    if g[0] == 0: return 1.0
    v = (g[0] + 2 * psum(g[1:])) / T
    if v <= 0: v = g[0] / T
    stat = mu / math.sqrt(v) * math.sqrt((T + 1 - 2 * hh + hh * (hh - 1) / T) / T)
    return float(2 * stats.t.sf(abs(stat), T - 1))


def combo(fns):
    def f(y, h, m):
        fs = [fn(y, h, m)[0] for fn in fns]
        return [psum(c[k] for c in fs) / len(fs) for k in range(h)], None
    return f


def tslm(y, h, m):
    def row(t): return [1.0, t + 1.0] + [1.0 if t % m == s else 0.0 for s in range(1, m)]
    X = np.array([row(t) for t in range(len(y))]); beta = np.linalg.lstsq(X, np.array(y), rcond=None)[0]
    return [float(np.dot(row(len(y) + k), beta)) for k in range(h)], {"slope": float(beta[1])}


METHODS = [("naive", naive, False), ("snaive", snaive, True), ("drift", drift, False), ("ma3", ma3, False),
           ("ses", ses, False), ("holt", holt, False), ("damped", damped, False), ("theta", theta, False), ("ridge", ridge, False), ("gbm", gbm, False), ("hw", hw, True), ("sarima", sarima, True),
           ("tslm", tslm, False), ("combS", combo([hw, sarima]), True), ("combN", combo([ses, holt, damped]), "N")]


def metrics(rec, scale):
    e = np.array([r[2] - r[3] for r in rec]); a = np.array([r[2] for r in rec]); f = np.array([r[3] for r in rec])
    mae = np.mean(np.abs(e)); mse = np.mean(e ** 2)
    return {"n": len(rec), "ME": float(np.mean(e)), "MAE": float(mae), "MSE": float(mse), "RMSE": math.sqrt(mse),
            "MAPE": None if np.any(a == 0) else float(100 * np.mean(np.abs(e / a))),
            "sMAPE": float(100 * np.mean(2 * np.abs(e) / (np.abs(a) + np.abs(f)))), "MASE": float(mae / scale)}


def load(path):
    with open(path) as fh: return [float(r["value"]) for r in csv.DictReader(fh)]


def run_all(y, m, max_test, max_h, future):
    """Fit each method once per origin with the longest horizon; truncating is exact
    because a k-step forecast does not depend on how many steps are requested."""
    n = len(y); fc = {}
    for mid, fn, seas in METHODS:
        if (seas is True and m == 1) or (seas == "N" and m > 1): continue
        fc[mid] = {T: fn(y[:T], max_h, m)[0] for T in range(n - max_test, n)}
        fc[mid]["future"] = fn(y, future, m)
    return fc


def train_scale(y, m, first):
    """MASE scale (Hyndman & Koehler 2006) with the fallbacks for a flat history:
    seasonal-naive MAE, then naive MAE, then the mean absolute level, then 1."""
    lag_mae = lambda L: float(np.mean([abs(y[t] - y[t - L]) for t in range(L, first)])) if first > L else 0.0
    lvl = float(np.mean(np.abs(y[:first]))); tiny = 1e-12 * (lvl or 1.0)
    sc = lag_mae(m)
    if sc > tiny: return sc
    if m > 1 and lag_mae(1) > tiny: return lag_mae(1)
    return lvl if lvl > 0 else 1.0


def evaluate(y, fc, m, test, h):
    n = len(y); first = n - test
    scale = train_scale(y, m, first)
    out = {}
    for mid in fc:
        rec = [(T, k, y[T + k - 1], fc[mid][T][k - 1]) for T in range(first, n) for k in range(1, h + 1) if T + k - 1 < n]
        loss = []
        for T in range(first, n):
            es = [abs(r[2] - r[3]) for r in rec if r[0] == T]
            loss.append(psum(es) / len(es) / scale)
        out[mid] = {"loss": loss, "metrics": metrics(rec, scale),
                    "maeByH": [metrics([r for r in rec if r[1] == k], scale)["MAE"] for k in range(1, h + 1)]}
    return scale, out


def main():
    js = json.load(open("js_results.json"))
    worst, checked = 0.0, 0
    cache = {}
    for case in js:
        y = load(case["file"]); m = case["m"]
        key = (case["file"], m)
        if key not in cache: cache[key] = run_all(y, m, 36, 12, 12)
        fc = cache[key]
        scale, py = evaluate(y, fc, m, case["test"], case["h"])
        pairs = [("scale", scale, case["scale"])]
        for r in case["results"]:
            p = py[r["id"]]
            for k, v in r["metrics"].items():
                pairs.append((f"{r['id']}.{k}", p["metrics"][k], v))
            for i, v in enumerate(r["maeByH"]): pairs.append((f"{r['id']}.maeH{i+1}", p["maeByH"][i], v))
            for i, v in enumerate(r["loss"]): pairs.append((f"{r['id']}.loss{i}", p["loss"][i], v))
            if r["id"] != "naive": pairs.append((f"{r['id']}.dm_vs_naive", dm_test(p["loss"], py["naive"]["loss"], case["h"]), r["dm"]))
            ff, pp = fc[r["id"]]["future"]
            for i, v in enumerate(r["future"]): pairs.append((f"{r['id']}.future{i+1}", ff[i], v))
            for k, v in (r["params"] or {}).items(): pairs.append((f"{r['id']}.{k}", pp[k], v))
        stab = []
        for w in (12, 24, 36):
            _, pw = evaluate(y, fc, m, w, case["h"])
            stab.append(min(pw, key=lambda k: (pw[k]["metrics"]["MASE"], pw[k]["metrics"]["RMSE"])))
        if stab != case["stability"]: print("STABILITY MISMATCH", case["label"], stab, case["stability"]); worst = math.inf
        for name, a, b in pairs:
            checked += 1
            if a is None or b is None:
                if a is not b: print("MISMATCH", case["label"], name, a, b); worst = math.inf
                continue
            rel = abs(a - b) / max(1.0, abs(a))
            worst = max(worst, rel)
            if rel > 1e-9: print("MISMATCH", case["label"], name, a, b)
    print(f"checked {checked} values across {len(js)} cases; worst relative difference {worst:.2e}")
    sys.exit(0 if worst <= 1e-9 else 1)


if __name__ == "__main__":
    main()
