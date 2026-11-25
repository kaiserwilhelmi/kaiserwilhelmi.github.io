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
  // Fitted as in forecast::ets (Hyndman & Khandakar, 2008): the smoothing weight on [1e-4, 0.9999]
  // and the starting level, by least squares (Nelder-Mead from the best grid value; the grid start
  // gives the old fit's SSE, so the fit can only improve).
  var LO = 1e-4, HI = 0.9999;
  function sesObj(y, p, keep) {
    var a = p[0], l = p[1], sse = 0;
    if (!(a >= LO && a <= HI)) return BIG;
    for (var t = 0; t < y.length; t++) { var e = y[t] - l; sse += e * e; l = l + a * e; }
    return keep ? l : sse;
  }
  function polish(f, x, steps, maxIter) { // Nelder-Mead, restarted from its own result until it stops improving
    var r = nelderMead(f, x, steps, maxIter, 1e-10);
    for (var i = 0; i < 5; i++) {
      var r2 = nelderMead(f, r.x, steps, maxIter, 1e-10);
      var done = !(r2.f < r.f - 1e-10 * (Math.abs(r.f) + 1e-10));
      if (r2.f <= r.f) r = r2;
      if (done) break;
    }
    return r;
  }
  function scaleOf(y) { return Math.max.apply(null, y) - Math.min.apply(null, y) || 1; }
  function ses(y, h) {
    var best = null, ba = 0;
    for (var i = 0; i < GRID.length; i++) {
      var r = sesRun(y, GRID[i]);
      if (best === null || r.sse < best.sse) { best = r; ba = GRID[i]; }
    }
    var f = function (p) { return sesObj(y, p, false); };
    var r1 = polish(f, [ba, y[0]], [0.05, 0.05 * scaleOf(y)], 1000), l = sesObj(y, r1.x, true);
    var o = []; for (var k = 0; k < h; k++) o.push(l);
    return { f: o, params: { alpha: r1.x[0] } };
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
  // Weights on [1e-4, 0.9999], phi on [0.80, 0.98] (damped) and the starting level and trend, fitted
  // together by least squares from the best grid point. The start l0 = y0 - (y1 - y0),
  // b0 = (y1 - y0) / phi reproduces the grid fit exactly, so the fit can only improve.
  function holtObj(y, p, damped, keep) {
    var a = p[0], b = p[1], phi = damped ? p[2] : 1, j = damped ? 3 : 2, l = p[j], tr = p[j + 1], sse = 0;
    if (!(a >= LO && a <= HI && b >= LO && b <= HI && (!damped || (phi >= 0.8 && phi <= 0.98)))) return BIG;
    for (var t = 0; t < y.length; t++) {
      var f = l + phi * tr, e = y[t] - f; sse += e * e;
      var ln = a * y[t] + (1 - a) * f;
      tr = b * (ln - l) + (1 - b) * phi * tr;
      l = ln;
    }
    return keep ? { l: l, b: tr, phi: phi } : sse;
  }
  function holtFit(y, h, phis) {
    var best = null, bp = null, damped = phis.length > 1;
    for (var p = 0; p < phis.length; p++)
      for (var i = 0; i < GRID.length; i++)
        for (var j = 0; j < GRID.length; j++) {
          var r = holtRun(y, GRID[i], GRID[j], phis[p]);
          if (best === null || r.sse < best.sse) { best = r; bp = { alpha: GRID[i], beta: GRID[j], phi: phis[p] }; }
        }
    var d0 = y[1] - y[0], sc = scaleOf(y), x0 = [bp.alpha, bp.beta], st = [0.05, 0.05];
    if (damped) { x0.push(bp.phi); st.push(0.02); }
    x0.push(y[0] - d0, d0 / bp.phi); st.push(0.05 * sc, 0.01 * sc);
    var r1 = polish(function (q) { return holtObj(y, q, damped, false); }, x0, st, 2000), fin = holtObj(y, r1.x, damped, true);
    var o = [], damp = 0, pk = 1;
    for (var k = 1; k <= h; k++) { pk *= fin.phi; damp += pk; o.push(fin.l + damp * fin.b); }
    return { f: o, params: { alpha: r1.x[0], beta: r1.x[1], phi: fin.phi } };
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
  // Phase 4 tested m - 1 free seasonal terms with restarts: a closer in-sample fit but 1-2% worse
  // forecasts on the 80 Market Watch series at 6 and 12 months, so this fit was kept.
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

  // ---- Theta method (Assimakopoulos & Nikolopoulos, 2000; Hyndman & Billah, 2003) ----
  // As in the M3/M4 benchmark: seasonal adjustment (classical decomposition) only when a
  // 90% autocorrelation test at lag m says the series is seasonal; then SES plus half the
  // linear-trend slope.
  function acf(y, k) {
    var mu = mean(y), num = 0, den = 0;
    for (var t = 0; t < y.length; t++) { den += (y[t] - mu) * (y[t] - mu); if (t >= k) num += (y[t] - mu) * (y[t - k] - mu); }
    return den === 0 ? 0 : num / den;
  }
  function seasonalTest(y, m) {
    if (m <= 1 || y.length < 3 * m) return false;
    var s = 0; for (var k = 1; k < m; k++) { var r = acf(y, k); s += r * r; }
    return Math.abs(acf(y, m)) > 1.645 * Math.sqrt((1 + 2 * s) / y.length);
  }
  function seasonalIndex(y, m, mult) {
    var n = y.length, half = Math.floor(m / 2), sums = [], cnt = [], t, j;
    for (j = 0; j < m; j++) { sums.push(0); cnt.push(0); }
    for (t = half; t < n - half; t++) {
      var s = 0;
      if (m % 2 === 0) { for (j = -half; j <= half; j++) s += (j === -half || j === half ? 0.5 : 1) * y[t + j]; }
      else { for (j = -half; j <= half; j++) s += y[t + j]; }
      s /= m;
      sums[t % m] += mult ? y[t] / s : y[t] - s; cnt[t % m]++;
    }
    var idx = sums.map(function (v, i) { return v / cnt[i]; }), c = mean(idx);
    return idx.map(function (v) { return mult ? v / c : v - c; });
  }
  function theta(y, h, m) {
    var n = y.length, seas = seasonalTest(y, m), mult = y.every(function (v) { return v > 0; }), t;
    var idx = seas ? seasonalIndex(y, m, mult) : null;
    var x = seas ? y.map(function (v, i) { return mult ? v / idx[i % m] : v - idx[i % m]; }) : y.slice();
    var tm = (n - 1) / 2, xm = mean(x), sxy = 0, sxx = 0;
    for (t = 0; t < n; t++) { sxy += (t - tm) * (x[t] - xm); sxx += (t - tm) * (t - tm); }
    var b0 = sxy / sxx, best = null;
    for (var i = 1; i <= 99; i++) {
      var a = i / 100, l = x[0], sse = 0;
      for (t = 1; t < n; t++) { var e = x[t] - l; sse += e * e; l += a * e; }
      if (best === null || sse < best.sse) best = { sse: sse, l: l, a: a };
    }
    // the SES part with its starting level fitted too (as in the optimised Theta method of
    // Fiorucci, Pellegrini, Louzada, Petropoulos & Koehler, 2016), from the best grid value
    var fr = polish(function (p) { return sesObj(x, p, false); }, [best.a, x[0]], [0.05, 0.05 * scaleOf(x)], 1000);
    best = { l: sesObj(x, fr.x, true), a: fr.x[0] };
    var o = [], decay = Math.pow(1 - best.a, n);
    for (var k = 1; k <= h; k++) {
      var v = best.l + 0.5 * b0 * ((1 - decay) / best.a + k - 1);
      if (seas) v = mult ? v * idx[(n + k - 1) % m] : v + idx[(n + k - 1) % m];
      o.push(v);
    }
    return { f: o, params: { alpha: best.a } };
  }

  // ---- intermittent demand (many zero periods) -------------------------------
  /* Demand pattern (Syntetos, Boylan & Croston, 2005): ADI = periods per period with demand, CV2 =
   * squared coefficient of variation of the non-zero sizes; cut-offs 1.32 and 0.49. A series that is
   * never negative, has at least two non-zero values and ADI > 1.32 ("intermittent" or "lumpy") gets
   * the three methods below and is ranked by squared error. */
  var ADI_CUT = 1.32, CV2_CUT = 0.49;
  function demandPattern(y) {
    var n = y.length, nz = [], i;
    for (i = 0; i < n; i++) { if (y[i] < 0) return null; if (y[i] > 0) nz.push(y[i]); }
    if (!nz.length) return { adi: Infinity, cv2: NaN, kind: "none", intermittent: false, nonzero: 0, n: n };
    var mu = mean(nz), v = 0;
    for (i = 0; i < nz.length; i++) v += (nz[i] - mu) * (nz[i] - mu);
    var adi = n / nz.length, cv2 = v / nz.length / (mu * mu), hiA = adi > ADI_CUT, hiC = cv2 > CV2_CUT;
    return { adi: adi, cv2: cv2, nonzero: nz.length, n: n, kind: hiA ? (hiC ? "lumpy" : "intermittent") : (hiC ? "erratic" : "smooth"),
      intermittent: hiA && nz.length >= 2 };
  }
  function isIntermittent(y) { var d = demandPattern(y); return !!(d && d.intermittent); }
  /* Croston (1972): smooth the non-zero sizes z and the intervals x between them separately and
   * forecast z / x. SBA (Syntetos & Boylan, 2005) multiplies by 1 - ax / 2 to remove Croston's
   * upward bias. TSB (Teunter, Syntetos & Babai, 2011) smooths the size on demand periods and the
   * probability of demand every period, and forecasts p * z, so the forecast decays when demand
   * stops. Following Kourentzes (2014): two smoothing weights on (0, 1], starting values fitted
   * too, by the rate-error cost r_t = forecast_t - (mean of y up to t): sum |r| (MAR) for Croston
   * and SBA, sum r^2 (MSR) for TSB. Search: the best of a small grid of weights with the "mean"
   * starting values (first size; mean interval or demand share), then Nelder-Mead. */
  var IGRID = [0.05, 0.1, 0.2, 0.3];
  function idStart(y) {
    var first = -1, last = -1, gaps = [], nz = 0, i;
    for (i = 0; i < y.length; i++) if (y[i] > 0) { gaps.push(i - last); if (first < 0) first = i; last = i; nz++; }
    return { z0: first < 0 ? 0 : y[first], x0: nz ? mean(gaps) : 1, p0: nz / y.length, nz: nz };
  }
  function crostonObj(y, p, sba, keep) {
    var az = p[0], ax = p[1], z = p[2], x = p[3], q = 1, cum = 0, cost = 0;
    if (!(az >= LO && az <= 1 && ax >= LO && ax <= 1 && z > 0 && x >= 1)) return BIG;
    var adj = sba ? 1 - ax / 2 : 1;
    for (var t = 0; t < y.length; t++) {
      cum += y[t];
      cost += Math.abs(adj * z / x - cum / (t + 1));
      if (y[t] > 0) { z += az * (y[t] - z); x += ax * (q - x); q = 1; } else q++;
    }
    return keep ? adj * z / x : cost;
  }
  function tsbObj(y, p, keep) {
    var az = p[0], ap = p[1], z = p[2], pr = p[3], cum = 0, cost = 0;
    if (!(az >= LO && az <= 1 && ap >= LO && ap <= 1 && z > 0 && pr >= 0 && pr <= 1)) return BIG;
    for (var t = 0; t < y.length; t++) {
      cum += y[t];
      var r = pr * z - cum / (t + 1); cost += r * r;
      if (y[t] > 0) { z += az * (y[t] - z); pr += ap * (1 - pr); } else pr += ap * (0 - pr);
    }
    return keep ? pr * z : cost;
  }
  function idFit(y, h, obj, second, step2, k2) {
    var st = idStart(y), o = [], k;
    if (st.nz === 0) { for (k = 0; k < h; k++) o.push(0); return { f: o, params: null }; }
    var best = null, bx = null;
    for (var i = 0; i < IGRID.length; i++)
      for (var j = 0; j < IGRID.length; j++) {
        var x0 = [IGRID[i], IGRID[j], st.z0, second], c = obj(x0, false);
        if (best === null || c < best) { best = c; bx = x0; }
      }
    var r = polish(function (q) { return obj(q, false); }, bx, [0.05, 0.05, 0.1 * st.z0, step2], 1000);
    var v = obj(r.x, true);
    for (k = 0; k < h; k++) o.push(v);
    var prm = { size_alpha: r.x[0] }; prm[k2] = r.x[1];
    return { f: o, params: prm };
  }
  function croston(y, h) { return idFit(y, h, function (q, keep) { return crostonObj(y, q, false, keep); }, idStart(y).x0, 0.5, "gap_alpha"); }
  function sba(y, h) { return idFit(y, h, function (q, keep) { return crostonObj(y, q, true, keep); }, idStart(y).x0, 0.5, "gap_alpha"); }
  function tsb(y, h) { return idFit(y, h, function (q, keep) { return tsbObj(y, q, keep); }, idStart(y).p0, 0.05, "chance_alpha"); }

  // ---- machine learning on recent changes --------------------------------------
  // Both learners predict the next period's change from the last p changes (p = m up to 13,
  // plus lag m for longer cycles), scaled by their root mean square, then forecast
  // recursively. With fewer than 10 training rows they fall back to the naive forecast.
  function lagsFor(m) { var L = [], p = m > 1 ? Math.min(m, 13) : 6; for (var i = 1; i <= p; i++) L.push(i); if (m > 13) L.push(m); return L; }
  function mlDesign(y, m) {
    var d = [], t; for (t = 1; t < y.length; t++) d.push(y[t] - y[t - 1]);
    return designFrom(d, m);
  }
  function designFrom(d, m) {
    var t;
    var L = lagsFor(m), maxL = L[L.length - 1], ss = 0;
    for (t = 0; t < d.length; t++) ss += d[t] * d[t];
    var sd = Math.sqrt(ss / d.length) || 1, z = d.map(function (v) { return v / sd; }), X = [], Y = [];
    for (t = maxL; t < z.length; t++) { X.push(L.map(function (l) { return z[t - l]; })); Y.push(z[t]); }
    return { z: z, X: X, Y: Y, L: L, sd: sd };
  }
  function mlForecast(y, h, D, predict) {
    var z = D.z.slice(), last = y[y.length - 1], o = [];
    for (var k = 0; k < h; k++) {
      var x = D.L.map(function (l) { return z[z.length - l]; }), dz = predict(x);
      z.push(dz); last += dz * D.sd; o.push(last);
    }
    return o;
  }
  function ridgeFit(X, Y, lam) {
    var p = X[0].length + 1, A = [], b = [], i, a, c;
    for (i = 0; i < p; i++) { A.push(new Array(p).fill(0)); b.push(0); }
    for (i = 0; i < X.length; i++) {
      var x = [1].concat(X[i]);
      for (a = 0; a < p; a++) { b[a] += x[a] * Y[i]; for (c = 0; c < p; c++) A[a][c] += x[a] * x[c]; }
    }
    for (a = 1; a < p; a++) A[a][a] += lam;
    return solve(A, b);
  }
  function ridgePredict(w, x) { var s = w[0]; for (var j = 0; j < x.length; j++) s += w[j + 1] * x[j]; return s; }
  // Ridge regression (Hoerl & Kennard, 1970): a linear autoregression with shrinkage; the
  // penalty is chosen on the last 20% of the training rows.
  // For a series that is always positive the changes are taken in logs (percentage changes), which
  // suits prices that grow in proportion; the forecast is turned back with exp.
  function ridge(y, h, m) {
    var pos = y.every(function (v) { return v > 0; }), ly = pos ? y.map(Math.log) : y, D = mlDesign(ly, m), N = D.X.length;
    if (N < 10) return naive(y, h);
    var nv = Math.max(4, Math.floor(N * 0.2)), Xt = D.X.slice(0, N - nv), Yt = D.Y.slice(0, N - nv), bestL = 1, bestE = null;
    [0.1, 1, 10, 100, 1000, 10000].forEach(function (lam) {
      var w = ridgeFit(Xt, Yt, lam), e = 0;
      for (var i = N - nv; i < N; i++) { var r = ridgePredict(w, D.X[i]) - D.Y[i]; e += r * r; }
      if (bestE === null || e < bestE) { bestE = e; bestL = lam; }
    });
    var w = ridgeFit(D.X, D.Y, bestL), f = mlForecast(ly, h, D, function (x) { return ridgePredict(w, x); });
    return { f: pos ? f.map(Math.exp) : f, params: { lambda: bestL, logs: pos ? 1 : 0 } };
  }
  // Gradient-boosted regression trees (Friedman, 2001): depth-2 trees, learning rate 0.05, squared
  // loss, minimum leaf size max(3, n/20). Exhaustive, deterministic splits. The number of trees
  // (25, 50, 100 or 150) is chosen on the last 20% of the training rows, the holdout ridge uses:
  // with a few hundred rows, 150 trees can overfit (early stopping; Friedman, 2001).
  var TREES = [25, 50, 100, 150];
  function gbmFit(X, Y, T, onTree) {
    var n = X.length, p = X[0].length, lr = 0.05, minLeaf = Math.max(3, Math.floor(n / 20)), i, j;
    var base = mean(Y), pred = new Array(n).fill(base), trees = [], order = [];
    for (j = 0; j < p; j++) {
      var ix = []; for (i = 0; i < n; i++) ix.push(i);
      (function (jj) { ix.sort(function (a, b) { return (X[a][jj] - X[b][jj]) || (a - b); }); })(j);
      order.push(ix);
    }
    function split(set, r) {
      var best = null, inSet = new Uint8Array(n), tot = 0, N = set.length;
      for (var q = 0; q < N; q++) { inSet[set[q]] = 1; tot += r[set[q]]; }
      for (var jj = 0; jj < p; jj++) {
        var ord = order[jj].filter(function (v) { return inSet[v] === 1; }), sl = 0, nl = 0;
        for (var kk = 0; kk < ord.length - 1; kk++) {
          sl += r[ord[kk]]; nl++;
          if (nl < minLeaf || N - nl < minLeaf) continue;
          if (X[ord[kk]][jj] === X[ord[kk + 1]][jj]) continue;
          var gain = sl * sl / nl + (tot - sl) * (tot - sl) / (N - nl);
          if (best === null || gain > best.gain) best = { gain: gain, j: jj, thr: (X[ord[kk]][jj] + X[ord[kk + 1]][jj]) / 2 };
        }
      }
      return best;
    }
    function leaf(set, r) { if (!set.length) return 0; var s = 0; for (var q = 0; q < set.length; q++) s += r[set[q]]; return s / set.length; }
    var all = []; for (i = 0; i < n; i++) all.push(i);
    for (var t = 0; t < T; t++) {
      var r = Y.map(function (v, q) { return v - pred[q]; }), s0 = split(all, r);
      if (s0 === null) break;
      var L = all.filter(function (q) { return X[q][s0.j] <= s0.thr; }), R = all.filter(function (q) { return X[q][s0.j] > s0.thr; });
      var kids = [L, R].map(function (set) {
        var s = split(set, r);
        if (s === null) return { v: leaf(set, r) };
        return { j: s.j, thr: s.thr, l: leaf(set.filter(function (q) { return X[q][s.j] <= s.thr; }), r), r: leaf(set.filter(function (q) { return X[q][s.j] > s.thr; }), r) };
      });
      var tree = { j: s0.j, thr: s0.thr, kids: kids };
      trees.push(tree);
      for (i = 0; i < n; i++) pred[i] += lr * treeEval(tree, X[i]);
      if (onTree) onTree(trees.length, base, trees);
    }
    return { base: base, trees: trees, lr: lr };
  }
  function gbmPredict(g, x) { var s = g.base; for (var k = 0; k < g.trees.length; k++) s += g.lr * treeEval(g.trees[k], x); return s; }
  function gbm(y, h, m) {
    var D = mlDesign(y, m), X = D.X, Y = D.Y, n = X.length;
    if (n < 10) return naive(y, h);
    var nv = Math.max(4, Math.floor(n * 0.2)), Xt = X.slice(0, n - nv), Yt = Y.slice(0, n - nv), bestT = TREES[TREES.length - 1], bestE = null;
    var hold = []; for (var i = n - nv; i < n; i++) hold.push(0);
    if (Xt.length >= 10) gbmFit(Xt, Yt, bestT, function (cnt, base, trees) {
      var tr = trees[cnt - 1], e = 0;
      for (var q = 0; q < nv; q++) { if (cnt === 1) hold[q] = base; hold[q] += 0.05 * treeEval(tr, X[n - nv + q]); var d = hold[q] - Y[n - nv + q]; e += d * d; }
      if (TREES.indexOf(cnt) >= 0 && (bestE === null || e < bestE)) { bestE = e; bestT = cnt; }
    });
    var g = gbmFit(X, Y, bestT);
    return { f: mlForecast(y, h, D, function (x) { return gbmPredict(g, x); }), params: { trees: g.trees.length } };
  }
  function treeEval(tr, x) { var kd = tr.kids[x[tr.j] <= tr.thr ? 0 : 1]; return "v" in kd ? kd.v : (x[kd.j] <= kd.thr ? kd.l : kd.r); }

  // ---- Diebold-Mariano test (Diebold & Mariano, 1995) -------------------------------------
  // Loss = per-origin mean absolute scaled error. The long-run variance is the equal-weighted
  // cosine (EWC) estimator with B = floor(0.4 T^(2/3)) and the p-value comes from Student's t
  // with B degrees of freedom (fixed-b; Lazarus, Lewis, Stock & Watson, 2018; Coroneo & Iacone,
  // 2020). With the 7 to 35 origins used here this keeps the false-alarm rate near 5%, where the
  // Harvey-Leybourne-Newbold version used before rejected up to 15% of the time.
  function betacf(a, b, x) {
    var qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap, h, m, m2, aa, del;
    if (Math.abs(d) < 1e-300) d = 1e-300; d = 1 / d; h = d;
    for (m = 1; m <= 300; m++) {
      m2 = 2 * m; aa = m * (b - m) * x / ((qam + m2) * (a + m2));
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; h *= d * c;
      aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; del = d * c; h *= del;
      if (Math.abs(del - 1) < 3e-16) break;
    }
    return h;
  }
  function lgamma(x) { // Lanczos
    var g = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    var y = x, tmp = x + 5.5; tmp -= (x + 0.5) * Math.log(tmp); var ser = 1.000000000190015;
    for (var j = 0; j < 6; j++) ser += g[j] / ++y;
    return -tmp + Math.log(2.5066282746310005 * ser / x);
  }
  function ibeta(a, b, x) {
    if (x <= 0) return 0; if (x >= 1) return 1;
    var bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
    return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b;
  }
  function tTwoSided(t, df) { return ibeta(df / 2, 0.5, df / (df + t * t)); }
  // Returns the two-sided p-value for "equal accuracy"; NaN when it cannot be tested.
  function dmTest(l1, l2) {
    var T = l1.length, d = [], mu = 0, spread = 0, i, j;
    for (i = 0; i < T; i++) { d.push(l1[i] - l2[i]); mu += d[i]; }
    mu /= T;
    for (i = 0; i < T; i++) spread = Math.max(spread, Math.abs(d[i] - mu));
    if (T < 2 || spread <= 1e-12 * Math.abs(mu)) return { p: mu === 0 ? 1 : NaN, stat: NaN, mean: mu, B: 0 };
    var B = Math.max(1, Math.floor(0.4 * Math.pow(T, 2 / 3))), om = 0;
    for (j = 1; j <= B; j++) {
      var L = 0;
      for (i = 0; i < T; i++) L += Math.cos(Math.PI * j * (i + 0.5) / T) * (d[i] - mu);
      L *= Math.sqrt(2 / T); om += L * L;
    }
    om /= B;
    if (!(om > 0)) return { p: NaN, stat: NaN, mean: mu, B: B };
    var stat = Math.sqrt(T) * mu / Math.sqrt(om);
    return { p: tTwoSided(stat, B), stat: stat, mean: mu, B: B };
  }
  // Holm (1979) step-down adjustment for a family of tests. NaN p-values are left out of the
  // family and stay NaN.
  function holm(ps) {
    var idx = [], out = ps.map(function () { return NaN; }), run = 0, i;
    for (i = 0; i < ps.length; i++) if (isFinite(ps[i])) idx.push(i);
    idx.sort(function (a, b) { return ps[a] - ps[b] || a - b; });
    idx.forEach(function (ix, r) { run = Math.max(run, Math.min(1, (idx.length - r) * ps[ix])); out[ix] = run; });
    return out;
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
    { id: "sarima", name: "Airline model (seasonal ARIMA)", seasonal: true, fn: sarima, ref: "Box & Jenkins (1970); FPP3 §9.9", note: "ARIMA(0,1,1)(0,1,1)m, one fixed model rather than a search: differences out trend and season, models what is left. Θ near −1 means the seasonal pattern barely changes." },
    { id: "theta", name: "Theta method", seasonal: false, fn: theta, ref: "Assimakopoulos & Nikolopoulos (2000); Hyndman & Billah (2003)", note: "Smoothed level plus half the long-run trend; seasonally adjusted when a test finds seasonality. M3 competition winner." },
    { id: "ridge", name: "ML: ridge regression", seasonal: false, ml: true, fn: ridge, ref: "Hoerl & Kennard (1970); FPP3 §9.3", note: "Machine learning: linear model of the next change from recent changes, with shrinkage. Handles exponential growth well." },
    { id: "gbm", name: "ML: boosted trees", seasonal: false, ml: true, fn: gbm, ref: "Friedman (2001); Makridakis et al. (2022)", note: "Machine learning: 150 small decision trees on recent changes; can capture non-linear patterns. The same model family won the M5 competition, but there it learned from thousands of related series; here it sees only this one." },
    { id: "tslm", name: "Regression: trend + season", seasonal: false, fn: tslm, ref: "FPP3 §7.4", note: "Least-squares line plus a dummy for each month." },
    { id: "combS", name: "Combination: HW + ARIMA", seasonal: true, fn: combo([hw, sarima]), parts: ["hw", "sarima"], ref: "Bates & Granger (1969); Makridakis et al. (2020)", note: "Average of Holt-Winters and seasonal ARIMA." },
    { id: "croston", name: "Croston", seasonal: false, intermittent: true, fn: croston, ref: "Croston (1972); Kourentzes (2014)", note: "For demand with many zero periods: smooths the order sizes and the gaps between orders separately; forecast = size / gap." },
    { id: "sba", name: "Syntetos-Boylan (SBA)", seasonal: false, intermittent: true, fn: sba, ref: "Syntetos & Boylan (2005)", note: "Croston with a correction for its known tendency to over-forecast." },
    { id: "tsb", name: "TSB", seasonal: false, intermittent: true, fn: tsb, ref: "Teunter, Syntetos & Babai (2011)", note: "Smooths the order size and the chance of an order each period, so the forecast falls when orders stop (useful for parts going obsolete)." },
    { id: "combN", name: "Combination: SES + Holt + damped", seasonal: false, nonseasonalOnly: true, fn: combo([ses, holt, damped]), parts: ["ses", "holt", "damped"], ref: "M4 benchmark; Makridakis et al. (2020)", note: "Average of the three smoothing methods." }
  ];

  // The intermittent-demand methods join only when y is intermittent (see demandPattern).
  function activeMethods(m, y) {
    var inter = !!y && isIntermittent(y);
    return METHODS.filter(function (d) { return (m > 1 ? !d.nonseasonalOnly : !d.seasonal) && (inter || !d.intermittent); });
  }

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
   * At each origin T every method is re-fitted on y[0..T-1] and forecasts 1..h steps ahead.
   * Only complete origins are scored: those whose whole h-step path lands inside the data, so
   * every step ahead is scored the same number of times. With a backtest window of N periods
   * the targets are the last N values and the origins run from n-N to n-h.
   * MASE scale = in-sample MAE of the seasonal naive (m = 1: naive) forecast on the data
   * before the first origin.
   * prepare() fits each origin once (12 steps); a k-step forecast does not depend on how many
   * steps were requested, so every horizon/window setting is scored from the same forecasts.
   * It fits twice the window: the older half lets the page test its own choice (see below). */
  var MAXH = 12, WINDOWS = [12, 24, 36];
  function maxWindow(n, m) { var w = 0; WINDOWS.forEach(function (x) { if (n - x >= minTrain(m)) w = x; }); return w; }
  // skip: indices of values that were filled in (interpolated gaps). They are used for fitting
  // but never scored as targets, so a method is not judged against a made-up number.
  // want: how many origins to fit (default: twice the longest window the series allows).
  function prepare(y, m, onProgress, skip, want) {
    var P = skeleton(y, m, skip);
    ensure(P, want || 2 * P.W, onProgress);
    P.fut = futures(y, m);
    return P;
  }
  // An empty backtest for y: checks the data and works out the longest window, fits nothing.
  function skeleton(y, m, skip) {
    var n = y.length, W = maxWindow(n, m), sk = {};
    for (var i0 = 0; i0 < n; i0++) if (typeof y[i0] !== "number" || !isFinite(y[i0])) throw new Error("Value " + (i0 + 1) + " of the series is not a number. Remove or fill it and try again.");
    (skip || []).forEach(function (i) { sk[i] = true; });
    if (!W) throw new Error("Need at least " + (minTrain(m) + 12) + " observations for this seasonality setting (have " + n + ").");
    var P = { y: y, m: m, W: W, meths: activeMethods(m, y), sq: isIntermittent(y), fc: {}, fut: null, skip: sk, nSkip: (skip || []).length, lo: n };
    P.meths.forEach(function (d) { P.fc[d.id] = {}; });
    return P;
  }
  // The 12-step forecasts from the end of the data, one per method.
  function futures(y, m) {
    var fut = {};
    var clip = isIntermittent(y);
    activeMethods(m, y).forEach(function (d) {
      fut[d.id] = d.parts ? { f: avg(d.parts.map(function (p) { return fut[p].f; })) } : floor0(d.fn(y, MAXH, m), clip);
    });
    return fut;
  }
  // Intermittent demand is never negative, so there every forecast is floored at zero, which can only
  // reduce each error (the other methods can dip below zero after a run of zeros).
  function floor0(r, on) { if (on) r.f = r.f.map(function (v) { return v < 0 ? 0 : v; }); return r; }
  function avg(arrs) { var o = []; for (var k = 0; k < arrs[0].length; k++) { var s = 0; for (var i = 0; i < arrs.length; i++) s += arrs[i][k]; o.push(s / arrs.length); } return o; }
  // Fit every method at origins lo .. hi-1 (newest first, so a progress bar moves evenly). A
  // combination averages the component forecasts already computed (the same numbers as refitting).
  // This is the slow part; the page runs it in a background worker.
  function fitRange(y, m, lo, hi, onProgress) {
    var meths = activeMethods(m, y), clip = isIntermittent(y), fc = {}, T, done = 0;
    meths.forEach(function (d) { fc[d.id] = {}; });
    for (T = hi - 1; T >= lo; T--) {
      var yt = y.slice(0, T);
      meths.forEach(function (d) { fc[d.id][T] = d.parts ? avg(d.parts.map(function (p) { return fc[p][T]; })) : floor0(d.fn(yt, MAXH, m), clip).f; });
      if (onProgress) onProgress(++done, hi - lo);
    }
    return fc;
  }
  function merge(P, fc, lo) {
    Object.keys(fc).forEach(function (id) { for (var T in fc[id]) P.fc[id][T] = fc[id][T]; });
    P.lo = Math.min(P.lo, lo);
  }
  // Lowest origin needed so that at least `want` origins exist, as far as the data allows.
  function loFor(P, want) { return Math.max(P.y.length - Math.max(want, P.W), minTrain(P.m)); }
  // Fit more (older) origins so that at least `want` origins exist. Returns true when it had to
  // fit anything.
  function ensure(P, want, onProgress) {
    var lo = loFor(P, want);
    if (lo >= P.lo) return false;
    merge(P, fitRange(P.y, P.m, lo, P.lo, onProgress), lo);
    return true;
  }
  // Ranking used everywhere on the page: lowest MAE (equivalently MASE) first, then lowest
  // RMSE, then method order. Anything not finite goes last.
  function cmpNum(x, y) { x = isFinite(x) ? x : Infinity; y = isFinite(y) ? y : Infinity; return x < y ? -1 : x > y ? 1 : 0; }

  /* score(): the table (each method over the window) plus two procedures that test the page's
   * own advice. At each scored origin T the procedures rank every method on the errors already
   * known at T (the N periods before T, complete origins only, exactly as the table ranks them
   * at the end of the data), then forecast with the top method ("pick") or the equal-weight
   * average of the top three ("pool"; Kourentzes, Barrow & Petropoulos, 2019). They are scored
   * on the same targets as the methods, so their numbers are free of the selection bias that
   * flatters the table's winner (Cawley & Talbot, 2010). */
  function score(P, opt) {
    var y = P.y, n = y.length, h = opt.h, m = P.m, test = opt.test, first = n - test, last = n - h;
    if (test > P.W) throw new Error("Backtest window of " + test + " needs " + (minTrain(m) + test) + " observations (have " + n + ").");
    if (test < 2 * h) throw new Error("A backtest window of " + test + " is too short for " + h + " steps ahead; use at least " + 2 * h + ".");
    var S = trainScale(y, m, first), scale = S.scale, sk = P.skip || {}, ids = P.meths.map(function (d) { return d.id; });
    function recordsOf(fcAt) {
      var rec = [];
      for (var T = first; T <= last; T++) {
        var f = fcAt(T);
        for (var k = 1; k <= h; k++) { var idx = T + k - 1; if (!sk[idx]) rec.push({ origin: T, k: k, idx: idx, y: y[idx], f: f[k - 1], e: y[idx] - f[k - 1] }); }
      }
      return rec;
    }
    function summary(rec) {
      var loss = [], q = 0;
      for (var T = first; T <= last; T++) {
        var s2 = 0, c2 = 0;
        for (; q < rec.length && rec[q].origin === T; q++) { s2 += P.sq ? rec[q].e * rec[q].e : Math.abs(rec[q].e); c2++; }
        if (c2) loss.push(P.sq ? s2 / c2 / (scale * scale) : s2 / c2 / scale); // an origin whose only targets were filled-in values has no loss
      }
      var byH = [], rByH = [];
      for (var k2 = 1; k2 <= h; k2++) { var mk = metrics(rec.filter(function (r) { return r.k === k2; }), scale); byH.push(mk.MAE); rByH.push(mk.RMSE); }
      return { metrics: metrics(rec, scale), maeByH: byH, rmseByH: rByH, loss: loss, records: rec };
    }
    var out = P.meths.map(function (d) {
      var r = summary(recordsOf(function (T) { return P.fc[d.id][T]; }));
      r.id = d.id; r.name = d.id === "tslm" && m === 1 ? "Regression: linear trend" : d.name; r.ref = d.ref; r.note = d.note;
      r.future = P.fut[d.id].f; r.params = P.fut[d.id].params || null;
      return r;
    });
    var ranked = rank(out, P.sq ? "RMSE" : "MASE"), top = ranked.slice(0, 3).map(function (r) { return r.id; });
    function poolAt(T, members) { return avg(members.map(function (id) { return P.fc[id][T]; })); }
    var res = { scale: scale, scaleBase: S.base, first: first, last: last, origins: last - first + 1, h: h, test: test, results: out, members: top,
      needN: minTrain(m) + 2 * test, rankBy: P.sq ? "RMSE" : "MASE", pool: null, pick: null, picks: null };
    // the pool with today's members over the whole window: used only when the history is too
    // short to test the choice, and labelled as optimistic there
    res.hindsight = summary(recordsOf(function (T) { return poolAt(T, top); }));
    res.hindsight.future = avg(top.map(function (id) { return P.fut[id].f; }));
    if (first - test < P.lo) return res;
    var picks = picksFor(P, h, test, first, last);
    res.pool = summary(recordsOf(function (T) { return poolAt(T, picks[T]); }));
    res.pool.future = res.hindsight.future;
    res.pick = summary(recordsOf(function (T) { return P.fc[picks[T][0]][T]; }));
    res.pick.future = P.fut[top[0]].f;
    res.picks = picks;
    return res;
  }
  /* picksFor(): the top three methods at each origin T in [from, to], ranked exactly as the table
   * ranks them but on the errors already known at T: complete origins T-test .. T-h, lowest total
   * absolute error first, then lowest squared error, then method order. Filled-in targets are
   * skipped. to may be n, the end of the data, where the picks are the table's own top three. */
  function picksFor(P, h, test, from, to) {
    var y = P.y, sk = P.skip || {}, ids = P.meths.map(function (d) { return d.id; }), sa = {}, sq = {}, picks = {}, T, k;
    if (from - test < P.lo) throw new Error("picksFor needs origins from " + (from - test) + "; fitted from " + P.lo + ".");
    ids.forEach(function (id) {
      sa[id] = {}; sq[id] = {};
      for (T = from - test; T <= to - h; T++) {
        var a = 0, b = 0, f = P.fc[id][T];
        for (k = 1; k <= h; k++) { var idx = T + k - 1; if (sk[idx]) continue; var e = y[idx] - f[k - 1]; a += Math.abs(e); b += e * e; }
        sa[id][T] = a; sq[id][T] = b;
      }
    });
    for (T = from; T <= to; T++) {
      var A = {}, Q = {};
      ids.forEach(function (id) { var a = 0, b = 0; for (var t = T - test; t <= T - h; t++) { a += sa[id][t]; b += sq[id][t]; } A[id] = a; Q[id] = b; });
      picks[T] = ids.map(function (id, i) { return { id: id, i: i }; }).sort(function (u, v) {
        return (P.sq ? cmpNum(Q[u.id], Q[v.id]) || cmpNum(A[u.id], A[v.id]) : cmpNum(A[u.id], A[v.id]) || cmpNum(Q[u.id], Q[v.id])) || u.i - v.i;
      }).slice(0, 3).map(function (u) { return u.id; });
    }
    return picks;
  }
  /* ranges(): forecast ranges for an approach ("pool", "pick" or "naive") from its own past errors:
   * empirical prediction intervals (Williams & Goodman, 1971; Lee & Scholtes, 2014). For each step
   * ahead k, the k-step errors the approach made at past origins, with the pool or pick re-chosen at
   * each origin exactly as it is chosen today, give quantiles that are added to today's forecast.
   * The check applies the same construction at every scored origin of the backtest window, using
   * only the errors already known there, and counts how often the actual landed inside: the
   * realised coverage the page shows next to each range.
   * opt: { h, test, kind, levels: [0.5, 0.8, ...], cal: errors per step to use (newest first) }. */
  var MINCAL = 10, CAL = 48;
  // Bounds of a central range from n sorted errors: the split-conformal order statistics (Lei,
  // G'Sell, Rinaldo, Tibshirani & Wasserman, 2018), which sit slightly outside the plain sample
  // quantiles so that a range from few errors is not too narrow. ok is false when there are too
  // few errors for the level (fewer than 39 for 95%); the bounds are then the smallest and largest.
  function confBounds(sorted, L) { // (the 1e-9 keeps 1 - 0.8 = 0.19999... from moving an exact rank)
    var n = sorted.length, a = 1 - L, il = Math.floor((n + 1) * a / 2 + 1e-9), iu = Math.ceil((n + 1) * (1 - a / 2) - 1e-9);
    return { lo: sorted[Math.max(il, 1) - 1], hi: sorted[Math.min(iu, n) - 1], ok: il >= 1 && iu <= n };
  }
  function ranges(P, opt) {
    var y = P.y, n = y.length, h = opt.h, test = opt.test, sk = P.skip || {}, kind = opt.kind, cal = opt.cal || CAL;
    var start = kind === "naive" ? P.lo : P.lo + test, picks = null, T, k;
    if (start > n - 1) return null;
    if (kind !== "naive") picks = picksFor(P, h, test, start, n - 1);
    function path(T2) {
      if (kind === "naive") return P.fc.naive[T2];
      return kind === "pick" ? P.fc[picks[T2][0]][T2] : avg(picks[T2].map(function (id) { return P.fc[id][T2]; }));
    }
    var paths = {}, errs = [];
    for (T = start; T < n; T++) paths[T] = path(T);
    for (k = 1; k <= h; k++) {
      var ek = [];
      for (T = start; T + k - 1 < n; T++) { var idx = T + k - 1; if (!sk[idx]) ek.push({ T: T, e: y[idx] - paths[T][k - 1] }); }
      errs.push(ek);
    }
    // quantiles of the k-step errors from origins up to `upto`, newest `cal` of them
    function bounds(k2, upto) {
      var ek2 = errs[k2 - 1], sel = [];
      for (var i = ek2.length - 1; i >= 0 && sel.length < cal; i--) if (ek2[i].T <= upto) sel.push(ek2[i].e);
      if (sel.length < MINCAL) return null;
      sel.sort(function (a, b) { return a - b; });
      return { n: sel.length, med: quantile(sel, 0.5), b: levels.map(function (L) { return confBounds(sel, L); }) };
    }
    // A series that never goes below zero (prices, demand) gets ranges floored at zero. Every actual
    // is then >= 0, so a clipped range holds exactly when the unclipped one does: coverage is
    // unchanged and the range only gets narrower.
    var nonneg = true;
    for (T = 0; T < n; T++) if (!sk[T] && !(y[T] >= 0)) { nonneg = false; break; }
    var fl = nonneg ? 0 : -Infinity;
    var levels = opt.levels, out = { kind: kind, start: start, levels: levels, floor: nonneg ? 0 : null, future: [], check: [], cover: {}, coverH: {}, nCheck: 0 };
    for (k = 1; k <= h; k++) {
      var b = bounds(k, n - k);
      out.future.push(b ? { n: b.n, p50: b.med, lo: b.b.map(function (x) { return x.lo; }), hi: b.b.map(function (x) { return x.hi; }), ok: b.b.map(function (x) { return x.ok; }) } : null);
    }
    // the check: scored origins of the backtest window, errors known at each origin only
    var first = n - test, last = n - h, hit = levels.map(function () { return 0; }), hitH = hit.slice(), above = hit.slice(), below = hit.slice(), cnt = 0, cntH = 0, nOrig = 0;
    for (T = Math.max(first, start); T <= last; T++) {
      var cnt0 = cnt;
      for (k = 1; k <= h; k++) {
        var idx2 = T + k - 1;
        if (sk[idx2]) continue;
        var b2 = bounds(k, T - k);
        if (!b2) continue;
        var f = paths[T][k - 1], row = { T: T, k: k, n: b2.n, f: f, y: y[idx2], p50: Math.max(f + b2.med, fl), lo: [], hi: [] };
        levels.forEach(function (L, li) {
          var lo = Math.max(f + b2.b[li].lo, fl), hi = Math.max(f + b2.b[li].hi, fl), inside = y[idx2] >= lo && y[idx2] <= hi;
          row.lo.push(lo); row.hi.push(hi);
          if (inside) { hit[li]++; if (k === h) hitH[li]++; } else if (y[idx2] > hi) above[li]++; else below[li]++;
        });
        out.check.push(row); cnt++; if (k === h) cntH++;
      }
      if (cnt > cnt0) nOrig++;
    }
    out.nCheck = cnt; out.nCheckH = cntH; out.nOrigins = nOrig;
    out.above = {}; out.below = {};
    levels.forEach(function (L, li) {
      out.cover[L] = cnt ? hit[li] / cnt : NaN; out.coverH[L] = cntH ? hitH[li] / cntH : NaN;
      out.above[L] = cnt ? above[li] / cnt : NaN; out.below[L] = cnt ? below[li] / cnt : NaN;
    });
    return out;
  }
  // Sample quantile with linear interpolation between order statistics (Hyndman & Fan, 1996,
  // type 7; the default in R and numpy). `sorted` must be in ascending order.
  function quantile(sorted, p) {
    var n = sorted.length; if (!n) return NaN;
    var x = (n - 1) * p, i = Math.floor(x), j = Math.min(i + 1, n - 1);
    return sorted[i] + (x - i) * (sorted[j] - sorted[i]);
  }
  /* MASE scale: in-sample MAE of the seasonal naive forecast (naive when m = 1) on the data
   * before the first origin (Hyndman & Koehler, 2006). When that is zero, as for a flat or
   * exactly repeating history, MASE is undefined, so fall back to the naive MAE and then to
   * the mean absolute level (Kolassa & Schütz, 2007). Rankings within a series do not change. */
  function trainScale(y, m, first) {
    function lagMAE(L) { var s = 0, c = 0; for (var t = L; t < first; t++) { s += Math.abs(y[t] - y[t - L]); c++; } return c ? s / c : 0; }
    var lvl = 0; for (var t = 0; t < first; t++) lvl += Math.abs(y[t]); lvl /= first;
    var tiny = 1e-12 * (lvl || 1), sc = lagMAE(m);
    if (sc > tiny) return { scale: sc, base: m > 1 ? "snaive" : "naive" };
    if (m > 1) { sc = lagMAE(1); if (sc > tiny) return { scale: sc, base: "naive" }; }
    return lvl > 0 ? { scale: lvl, base: "level" } : { scale: 1, base: "none" };
  }
  function backtest(y, opt) { return score(prepare(y, opt.m), opt); }

  // lowest MASE wins and RMSE breaks ties (by = "RMSE", used for intermittent demand: the other way
  // round); then method order; anything not finite goes last
  function rank(results, by) {
    var k1 = by === "RMSE" ? "RMSE" : "MASE", k2 = k1 === "RMSE" ? "MASE" : "RMSE";
    return results.map(function (r, i) { return { r: r, i: i }; }).sort(function (a, b) {
      return cmpNum(a.r.metrics[k1], b.r.metrics[k1]) || cmpNum(a.r.metrics[k2], b.r.metrics[k2]) || a.i - b.i;
    }).map(function (o) { return o.r; });
  }

  var api = { demandPattern: demandPattern, isIntermittent: isIntermittent, ADI_CUT: ADI_CUT, CV2_CUT: CV2_CUT, ranges: ranges, confBounds: confBounds, MINCAL: MINCAL, CAL: CAL, quantile: quantile, skeleton: skeleton, futures: futures, fitRange: fitRange, merge: merge, loFor: loFor, picksFor: picksFor, dmTest: dmTest, holm: holm, tTwoSided: tTwoSided, ensure: ensure, METHODS: METHODS, activeMethods: activeMethods, backtest: backtest, prepare: prepare, score: score, WINDOWS: WINDOWS, MAXH: MAXH, metrics: metrics, rank: rank, minTrain: minTrain, GRID: GRID, PHI: PHI };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.FCEngine = api;
})(this);
