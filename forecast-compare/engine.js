/* Forecast engine: methods, rolling-origin backtest, accuracy metrics.
 * Runs in the browser and in Node (verify step). No dependencies.
 * Methods and metrics follow Hyndman & Athanasopoulos, Forecasting: Principles
 * and Practice (3rd ed., 2021) and Hyndman & Koehler (2006). Smoothing
 * parameters are chosen by a fixed grid search that minimises in-sample
 * one-step squared error, so results are deterministic and reproducible.
 */
(function (root) {
  "use strict";
  var GRID = [];
  for (var i = 0; i < 10; i++) GRID.push((2 * i + 1) / 20); // 0.05 .. 0.95
  var PHI = [0.8, 0.85, 0.9, 0.95, 0.98];

  function mean(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s / a.length; }

  // ---- simple benchmarks -------------------------------------------------
  function naive(y, h) { var v = y[y.length - 1], o = []; for (var k = 0; k < h; k++) o.push(v); return { f: o }; }
  function snaive(y, h, m) {
    var T = y.length, o = [];
    for (var k = 1; k <= h; k++) o.push(y[T - m + ((k - 1) % m)]);
    return { f: o };
  }
  function drift(y, h) {
    var T = y.length, last = y[T - 1], slope = (last - y[0]) / (T - 1), o = [];
    for (var k = 1; k <= h; k++) o.push(last + k * slope);
    return { f: o };
  }
  function movavg(y, h) {
    var q = 3, v = (y[y.length - 1] + y[y.length - 2] + y[y.length - 3]) / q, o = [];
    for (var k = 0; k < h; k++) o.push(v);
    return { f: o };
  }

  // ---- exponential smoothing --------------------------------------------
  function sesRun(y, a) {
    var l = y[0], sse = 0;
    for (var t = 1; t < y.length; t++) { var e = y[t] - l; sse += e * e; l = l + a * e; }
    return { sse: sse, l: l };
  }
  function ses(y, h) {
    var best = null, ba = 0;
    for (var i = 0; i < GRID.length; i++) {
      var r = sesRun(y, GRID[i]);
      if (best === null || r.sse < best.sse) { best = r; ba = GRID[i]; }
    }
    var o = []; for (var k = 0; k < h; k++) o.push(best.l);
    return { f: o, params: { alpha: ba } };
  }

  // Holt's linear trend (phi = 1) and Gardner-McKenzie damped trend.
  function holtRun(y, a, b, phi) {
    var l = y[0], tr = y[1] - y[0], sse = 0;
    for (var t = 1; t < y.length; t++) {
      var f = l + phi * tr, e = y[t] - f; sse += e * e;
      var ln = a * y[t] + (1 - a) * (l + phi * tr);
      tr = b * (ln - l) + (1 - b) * phi * tr;
      l = ln;
    }
    return { sse: sse, l: l, b: tr };
  }
  function holtFit(y, h, phis) {
    var best = null, bp = null;
    for (var p = 0; p < phis.length; p++)
      for (var i = 0; i < GRID.length; i++)
        for (var j = 0; j < GRID.length; j++) {
          var r = holtRun(y, GRID[i], GRID[j], phis[p]);
          if (best === null || r.sse < best.sse) { best = r; bp = { alpha: GRID[i], beta: GRID[j], phi: phis[p] }; }
        }
    var o = [], damp = 0, pk = 1;
    for (var k = 1; k <= h; k++) { pk *= bp.phi; damp += pk; o.push(best.l + damp * best.b); }
    return { f: o, params: bp };
  }
  function holt(y, h) { var r = holtFit(y, h, [1]); delete r.params.phi; return r; }
  function damped(y, h) { return holtFit(y, h, PHI); }

  // ---- Nelder-Mead simplex minimiser (Nelder & Mead, 1965) --------------
  // Fixed iteration cap and only + - * / arithmetic, so the browser and the
  // Python check follow exactly the same path.
  var BIG = 1e300;
  function nelderMead(f, x0, steps, maxIter, tol) {
    var n = x0.length, pts = [x0.slice()], vals, i, j, it;
    for (i = 0; i < n; i++) { var p = x0.slice(); p[i] = x0[i] + steps[i]; pts.push(p); }
    vals = pts.map(f);
    for (it = 0; it < maxIter; it++) {
      var ord = []; for (i = 0; i <= n; i++) ord.push(i);
      ord.sort(function (a, b) { return vals[a] < vals[b] ? -1 : vals[a] > vals[b] ? 1 : a - b; });
      pts = ord.map(function (k) { return pts[k]; }); vals = ord.map(function (k) { return vals[k]; });
      if (Math.abs(vals[n] - vals[0]) <= tol * (Math.abs(vals[0]) + tol)) break;
      var c = [];
      for (j = 0; j < n; j++) { var s = 0; for (i = 0; i < n; i++) s += pts[i][j]; c.push(s / n); }
      var xr = [], xe = [], xc = [];
      for (j = 0; j < n; j++) xr.push(c[j] + (c[j] - pts[n][j]));
      var fr = f(xr);
      if (fr < vals[0]) {
        for (j = 0; j < n; j++) xe.push(c[j] + 2 * (c[j] - pts[n][j]));
        var fe = f(xe);
        if (fe < fr) { pts[n] = xe; vals[n] = fe; } else { pts[n] = xr; vals[n] = fr; }
      } else if (fr < vals[n - 1]) { pts[n] = xr; vals[n] = fr; }
      else {
        var fc, ok;
        if (fr < vals[n]) { for (j = 0; j < n; j++) xc.push(c[j] + 0.5 * (xr[j] - c[j])); fc = f(xc); ok = fc <= fr; }
        else { for (j = 0; j < n; j++) xc.push(c[j] + 0.5 * (pts[n][j] - c[j])); fc = f(xc); ok = fc < vals[n]; }
        if (ok) { pts[n] = xc; vals[n] = fc; }
        else for (i = 1; i <= n; i++) {
          var q = []; for (j = 0; j < n; j++) q.push(pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]));
          pts[i] = q; vals[i] = f(q);
        }
      }
    }
    var bi = 0; for (i = 1; i <= n; i++) if (vals[i] < vals[bi]) bi = i;
    return { x: pts[bi], f: vals[bi] };
  }

  // ---- Holt-Winters additive: weights AND starting states fitted ----------
  // Parameters: alpha, beta, gamma, initial level, initial trend, m initial
  // seasonal terms, all chosen together to minimise one-step squared error
  // (the least-squares analogue of the ETS(A,A,A) fit in FPP3 §8.3/§8.6).
  function hwRun(y, m, p, keep) {
    var a = p[0], b = p[1], g = p[2], l = p[3], tr = p[4];
    if (!(a > 0 && a < 1 && b > 0 && b < 1 && g > 0 && g < 1)) return BIG;
    var s = p.slice(5, 5 + m), sse = 0;
    for (var t = 0; t < y.length; t++) {
      var e = y[t] - (l + tr + s[t]); sse += e * e;
      var ln = a * (y[t] - s[t]) + (1 - a) * (l + tr);
      tr = b * (ln - l) + (1 - b) * tr;
      s.push(g * (y[t] - ln) + (1 - g) * s[t]);
      l = ln;
    }
    return keep ? { l: l, b: tr, s: s, sse: sse } : sse;
  }
  function hw(y, h, m) {
    var i, l0 = mean(y.slice(0, m)), b0 = (mean(y.slice(m, 2 * m)) - l0) / m;
    var x0 = [0.3, 0.1, 0.1, l0 - (m + 1) / 2 * b0, b0];
    for (i = 0; i < m; i++) x0.push(y[i] - (l0 + (i - (m - 1) / 2) * b0));
    var sc = Math.max.apply(null, y) - Math.min.apply(null, y) || 1;
    var steps = [0.1, 0.05, 0.05, 0.05 * sc, 0.01 * sc];
    for (i = 0; i < m; i++) steps.push(0.05 * sc);
    var r = nelderMead(function (p) { return hwRun(y, m, p, false); }, x0, steps, 3000, 1e-10);
    var st = hwRun(y, m, r.x, true), T = y.length, o = [];
    for (var k = 1; k <= h; k++) o.push(st.l + k * st.b + st.s[T + ((k - 1) % m)]);
    return { f: o, params: { alpha: r.x[0], beta: r.x[1], gamma: r.x[2] } };
  }

  // ---- Seasonal ARIMA(0,1,1)(0,1,1)m, the "airline model" -----------------
  // Box & Jenkins (1970); FPP3 §9.9. Fitted by conditional sum of squares.
  function sarimaRun(y, m, th, TH, keep) {
    if (!(th > -1 && th < 1 && TH > -1 && TH < 1)) return BIG;
    var n = y.length, e = new Array(n).fill(0), sse = 0;
    for (var t = m + 1; t < n; t++) {
      var w = y[t] - y[t - 1] - y[t - m] + y[t - m - 1];
      var et = w - th * e[t - 1] - TH * e[t - m] - th * TH * e[t - m - 1];
      e[t] = et; sse += et * et;
    }
    return keep ? e : sse;
  }
  function sarima(y, h, m) {
    var r = nelderMead(function (p) { return sarimaRun(y, m, p[0], p[1], false); }, [-0.3, -0.5], [0.2, 0.2], 500, 1e-10);
    var th = r.x[0], TH = r.x[1], e = sarimaRun(y, m, th, TH, true), yy = y.slice(), n = y.length;
    for (var k = 0; k < h; k++) {
      var t = n + k, w = th * e[t - 1] + TH * e[t - m] + th * TH * e[t - m - 1];
      e.push(0); yy.push(yy[t - 1] + yy[t - m] - yy[t - m - 1] + w);
    }
    return { f: yy.slice(n), params: { theta: th, Theta: TH } };
  }

  // ---- equal-weight combinations (Bates & Granger, 1969) ------------------
  function combo(fns) {
    return function (y, h, m) {
      var fs = fns.map(function (fn) { return fn(y, h, m).f; }), o = [];
      for (var k = 0; k < h; k++) { var s = 0; for (var i = 0; i < fs.length; i++) s += fs[i][k]; o.push(s / fs.length); }
      return { f: o };
    };
  }

  // ---- regression: linear trend + seasonal dummies (OLS) -----------------
  function solve(A, bv) { // Gaussian elimination, partial pivoting
    var n = bv.length, M = A.map(function (r, i) { return r.slice().concat([bv[i]]); });
    for (var c = 0; c < n; c++) {
      var p = c;
      for (var r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      var tmp = M[c]; M[c] = M[p]; M[p] = tmp;
      for (var r2 = c + 1; r2 < n; r2++) {
        var f = M[r2][c] / M[c][c];
        for (var cc = c; cc <= n; cc++) M[r2][cc] -= f * M[c][cc];
      }
    }
    var x = new Array(n);
    for (var i = n - 1; i >= 0; i--) {
      var s = M[i][n];
      for (var j = i + 1; j < n; j++) s -= M[i][j] * x[j];
      x[i] = s / M[i][i];
    }
    return x;
  }
  function regRow(t, m) { // t is 0-based time index
    var r = [1, t + 1];
    for (var s = 1; s < m; s++) r.push(t % m === s ? 1 : 0);
    return r;
  }
  function tslm(y, h, m) {
    var p = 1 + m, XtX = [], Xty = [];
    for (var i = 0; i < p; i++) { XtX.push(new Array(p).fill(0)); Xty.push(0); }
    for (var t = 0; t < y.length; t++) {
      var r = regRow(t, m);
      for (var a = 0; a < p; a++) { Xty[a] += r[a] * y[t]; for (var b = 0; b < p; b++) XtX[a][b] += r[a] * r[b]; }
    }
    var beta = solve(XtX, Xty), o = [];
    for (var k = 0; k < h; k++) {
      var rr = regRow(y.length + k, m), v = 0;
      for (var c = 0; c < p; c++) v += rr[c] * beta[c];
      o.push(v);
    }
    return { f: o, params: { slope: beta[1] } };
  }

  var METHODS = [
    { id: "naive", name: "Naive", seasonal: false, fn: naive, ref: "FPP3 §5.2", note: "Next value = last value. The benchmark every method must beat." },
    { id: "snaive", name: "Seasonal naive", seasonal: true, fn: snaive, ref: "FPP3 §5.2", note: "Next value = same month last year." },
    { id: "drift", name: "Drift", seasonal: false, fn: drift, ref: "FPP3 §5.2", note: "Extends the straight line from first to last observation." },
    { id: "ma3", name: "3-month moving average", seasonal: false, fn: movavg, ref: "FPP3 §3.3", note: "Flat forecast at the average of the last 3 values." },
    { id: "ses", name: "Simple exponential smoothing", seasonal: false, fn: ses, ref: "FPP3 §8.1", note: "Weighted average with weights decaying by α." },
    { id: "holt", name: "Holt linear trend", seasonal: false, fn: holt, ref: "Holt (1957/2004); FPP3 §8.2", note: "Smoothed level plus smoothed trend." },
    { id: "damped", name: "Damped trend", seasonal: false, fn: damped, ref: "Gardner & McKenzie (1985); FPP3 §8.2", note: "Holt with the trend flattening out by φ each period." },
    { id: "hw", name: "Holt-Winters additive", seasonal: true, fn: hw, ref: "Winters (1960); FPP3 §8.3", note: "Level, trend and a repeating seasonal pattern; weights and starting values fitted together." },
    { id: "sarima", name: "Seasonal ARIMA", seasonal: true, fn: sarima, ref: "Box & Jenkins (1970); FPP3 §9.9", note: "ARIMA(0,1,1)(0,1,1)m: differences out trend and season, models what is left." },
    { id: "tslm", name: "Regression: trend + season", seasonal: false, fn: tslm, ref: "FPP3 §7.4", note: "Least-squares line plus a dummy for each month." },
    { id: "combS", name: "Combination: HW + ARIMA", seasonal: true, fn: combo([hw, sarima]), parts: ["hw", "sarima"], ref: "Bates & Granger (1969); Makridakis et al. (2020)", note: "Average of Holt-Winters and seasonal ARIMA." },
    { id: "combN", name: "Combination: SES + Holt + damped", seasonal: false, nonseasonalOnly: true, fn: combo([ses, holt, damped]), parts: ["ses", "holt", "damped"], ref: "M4 benchmark; Makridakis et al. (2020)", note: "Average of the three smoothing methods." }
  ];

  function activeMethods(m) { return METHODS.filter(function (d) { return m > 1 ? !d.nonseasonalOnly : !d.seasonal; }); }

  function minTrain(m) { return Math.max(2 * m + 2, 6); }

  // ---- metrics -------------------------------------------------------------
  function metrics(rec, scale) {
    var n = rec.length, me = 0, mae = 0, mse = 0, mape = 0, smape = 0, zero = false;
    for (var i = 0; i < n; i++) {
      var e = rec[i].e, a = rec[i].y, f = rec[i].f;
      me += e; mae += Math.abs(e); mse += e * e;
      if (a === 0) zero = true; else mape += Math.abs(e / a);
      var d = Math.abs(a) + Math.abs(f);
      smape += d === 0 ? 0 : 2 * Math.abs(e) / d;
    }
    me /= n; mae /= n; mse /= n;
    return { n: n, ME: me, MAE: mae, MSE: mse, RMSE: Math.sqrt(mse),
      MAPE: zero ? null : 100 * mape / n, sMAPE: 100 * smape / n, MASE: mae / scale };
  }

  /* Rolling-origin evaluation (Tashman 2000; FPP3 §5.10).
   * For each origin T = n-test .. n-1 every method is re-fitted on y[0..T-1]
   * and forecasts 1..h steps ahead; forecasts that land inside the data are
   * scored. MASE scale = in-sample MAE of the seasonal naive (m=1: naive)
   * forecast on the training data before the first origin.
   * prepare() fits every origin once (longest window, 12 steps); a k-step
   * forecast does not depend on how many steps were requested, so every
   * horizon/window setting is then scored from the same forecasts. */
  var MAXH = 12, WINDOWS = [12, 24, 36];
  function maxWindow(n, m) { var w = 0; WINDOWS.forEach(function (x) { if (n - x >= minTrain(m)) w = x; }); return w; }
  function prepare(y, m, onProgress) {
    var n = y.length, W = maxWindow(n, m);
    if (!W) throw new Error("Need at least " + (minTrain(m) + 12) + " observations for this seasonality setting (have " + n + ").");
    var meths = activeMethods(m), fc = {}, fut = {};
    function avg(arrs) { var o = []; for (var k = 0; k < MAXH; k++) { var s = 0; for (var i = 0; i < arrs.length; i++) s += arrs[i][k]; o.push(s / arrs.length); } return o; }
    meths.forEach(function (d) {
      fc[d.id] = {};
      if (d.parts) { // a combination: average the component forecasts already computed (same numbers as refitting)
        for (var T0 = n - W; T0 < n; T0++) fc[d.id][T0] = avg(d.parts.map(function (p) { return fc[p][T0]; }));
        fut[d.id] = { f: avg(d.parts.map(function (p) { return fut[p].f; })) };
      } else {
        for (var T = n - W; T < n; T++) fc[d.id][T] = d.fn(y.slice(0, T), MAXH, m).f;
        fut[d.id] = d.fn(y, MAXH, m);
      }
      if (onProgress) onProgress(d.id);
    });
    return { y: y, m: m, W: W, meths: meths, fc: fc, fut: fut };
  }
  function score(P, opt) {
    var y = P.y, n = y.length, h = opt.h, m = P.m, test = opt.test, first = n - test;
    if (test > P.W) throw new Error("Backtest window of " + test + " needs " + (minTrain(m) + test) + " observations (have " + n + ").");
    var sc = 0, cnt = 0;
    for (var t = m; t < first; t++) { sc += Math.abs(y[t] - y[t - m]); cnt++; }
    var scale = sc / cnt, out = [];
    P.meths.forEach(function (d) {
      var rec = [];
      for (var T = first; T < n; T++) {
        var f = P.fc[d.id][T];
        for (var k = 1; k <= h; k++) {
          var idx = T + k - 1;
          if (idx < n) rec.push({ origin: T, k: k, idx: idx, y: y[idx], f: f[k - 1], e: y[idx] - f[k - 1] });
        }
      }
      var byH = [];
      for (var k2 = 1; k2 <= h; k2++) byH.push(metrics(rec.filter(function (r) { return r.k === k2; }), scale).MAE);
      out.push({ id: d.id, name: d.id === "tslm" && m === 1 ? "Regression: linear trend" : d.name, ref: d.ref, note: d.note, metrics: metrics(rec, scale),
        maeByH: byH, future: P.fut[d.id].f, params: P.fut[d.id].params || null, records: rec });
    });
    return { scale: scale, first: first, results: out };
  }
  function backtest(y, opt) { return score(prepare(y, opt.m), opt); }

  // Does the winner hold up when the backtest window changes?
  function stability(P, h) {
    var rows = WINDOWS.filter(function (w) { return w <= P.W; }).map(function (w) {
      var r = rank(score(P, { h: h, test: w }).results);
      return { test: w, winner: r[0].id, name: r[0].name, top3: r.slice(0, 3).map(function (x) { return x.id; }) };
    });
    return rows;
  }

  function rank(results) { // lowest MASE wins; RMSE breaks ties
    return results.slice().sort(function (a, b) {
      return (a.metrics.MASE - b.metrics.MASE) || (a.metrics.RMSE - b.metrics.RMSE);
    });
  }

  var api = { METHODS: METHODS, activeMethods: activeMethods, backtest: backtest, prepare: prepare, score: score, stability: stability, WINDOWS: WINDOWS, MAXH: MAXH, metrics: metrics, rank: rank, minTrain: minTrain, GRID: GRID, PHI: PHI };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.FCEngine = api;
})(this);
