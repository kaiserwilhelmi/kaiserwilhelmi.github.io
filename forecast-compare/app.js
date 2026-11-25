/* UI for the forecast comparison page. Depends on FCEngine (engine.js) and SERIES (inlined data). */
(function () {
  "use strict";
  var E = window.FCEngine, SERIES = window.SERIES, MW = window.MW_CATALOG || { groups: [], items: [] }, MK = window.FCMarket;
  var $ = function (id) { return document.getElementById(id); };
  var state = { key: SERIES[0].key, upload: null, h: 6, test: 24, m: 12, compare: "naive", view: "recent", dots: "1", more: false, sort: "rank", dir: 1 };
  var last = null;

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function digits(v) { var a = Math.abs(v); return a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4; }
  function fmt(v, d) { if (v === null || v === undefined || !isFinite(v)) return "n/a"; return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function fmtV(v, ref) { return fmt(v, digits(ref === undefined ? v : ref)); }

  // ---- dates --------------------------------------------------------------
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function parseYM(s) { var m = /^(\d{4})-(\d{1,2})/.exec(s); return m ? { y: +m[1], m: +m[2] } : null; }
  function label(s) { var p = parseYM(s); return p ? MON[p.m - 1] + " " + p.y : s; }
  function one(s) { return s.unitOne || "month"; }
  function many(s) { return s.unitMany || "months"; }
  function futureDates(dates, k, s) {
    if (s && s.future) return s.future(k);
    var a = parseYM(dates[dates.length - 2]), b = parseYM(dates[dates.length - 1]), out = [];
    if (!a || !b) { for (var i = 1; i <= k; i++) out.push("t+" + i); return out; }
    var step = (b.y - a.y) * 12 + (b.m - a.m) || 1, cur = b.y * 12 + b.m - 1;
    for (var j = 1; j <= k; j++) { var c = cur + j * step; out.push(Math.floor(c / 12) + "-" + String(c % 12 + 1).padStart(2, "0") + "-01"); }
    return out;
  }

  // ---- data ---------------------------------------------------------------
  function current() {
    if (state.key === "upload" && state.upload) return state.upload;
    if (loaded[state.key]) return loaded[state.key];
    return SERIES.filter(function (s) { return s.key === state.key; })[0];
  }
  // ---- charts (inline SVG) -----------------------------------------------
  function lineChart(el, cfg) {
    var W = el.clientWidth || 720, H = cfg.height || 300, pad = { l: 56, r: 16, t: 12, b: 28 };
    var n = cfg.labels.length, ys = [];
    cfg.series.forEach(function (s) { s.pts.forEach(function (p) { if (p[1] !== null) ys.push(p[1]); }); });
    (cfg.bands || []).forEach(function (b) { b.lo.concat(b.hi).forEach(function (p) { if (isFinite(p[1])) ys.push(p[1]); }); });
    var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys), span = hi - lo || 1;
    lo -= span * 0.06; hi += span * 0.06;
    if (cfg.zero) lo = 0;
    var X = function (i) { return pad.l + (n === 1 ? 0 : i * (W - pad.l - pad.r) / (n - 1)); };
    var Y = function (v) { return pad.t + (hi - v) * (H - pad.t - pad.b) / (hi - lo); };
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '" role="img" aria-label="' + esc(cfg.aria) + '">';
    if (cfg.band) s += '<rect x="' + X(cfg.band[0]) + '" y="' + pad.t + '" width="' + (X(cfg.band[1]) - X(cfg.band[0])) + '" height="' + (H - pad.t - pad.b) + '" fill="var(--band)"/>' +
      '<text x="' + (X(cfg.band[0]) + 6) + '" y="' + (pad.t + 14) + '" class="ax">' + esc(cfg.bandLabel) + "</text>";
    for (var g = 0; g <= 4; g++) {
      var v = lo + (hi - lo) * g / 4, yy = Y(v);
      s += '<line x1="' + pad.l + '" x2="' + (W - pad.r) + '" y1="' + yy + '" y2="' + yy + '" stroke="var(--grid)"/>' +
        '<text x="' + (pad.l - 8) + '" y="' + (yy + 4) + '" text-anchor="end" class="ax">' + fmtV(v, hi - lo) + "</text>";
    }
    // x labels: evenly spaced, skipping any that would run into the one before (about 6.2 px per character at 11 px)
    var every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - pad.l) / 70)))), right = -Infinity;
    for (var i = 0; i < n; i += every) {
      var txt = cfg.xfmt(cfg.labels[i]), wd = 6.2 * String(txt).length, anc = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
      var x0 = anc === "start" ? X(i) : anc === "end" ? X(i) - wd : X(i) - wd / 2;
      if (x0 < right + 8 || x0 + wd > W) continue;
      right = x0 + wd;
      s += '<text x="' + X(i) + '" y="' + (H - 8) + '" text-anchor="' + anc + '" class="ax">' + esc(txt) + "</text>";
    }
    (cfg.bands || []).forEach(function (b) { // forecast ranges: filled between lower and upper bounds
      var d = b.lo.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); }).join("") +
        b.hi.slice().reverse().map(function (p) { return "L" + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); }).join("") + "Z";
      s += '<path d="' + d + '" fill="' + b.color + '" fill-opacity="' + b.opacity + '" stroke="none"/>';
    });
    cfg.series.forEach(function (se) {
      var d = "", pen = false;
      se.pts.forEach(function (p) { if (p[1] === null) { pen = false; return; } d += (pen ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1); pen = true; });
      s += '<path d="' + d + '" fill="none" stroke="' + se.color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"' + (se.dash ? ' stroke-dasharray="5 4"' : "") + "/>";
      if (se.dots) se.pts.forEach(function (p) { if (p[1] !== null) s += '<circle cx="' + X(p[0]) + '" cy="' + Y(p[1]) + '" r="3" fill="' + se.color + '" stroke="var(--surface)" stroke-width="2"/>'; });
    });
    s += '<line class="xh" x1="0" x2="0" y1="' + pad.t + '" y2="' + (H - pad.b) + '" stroke="var(--text-3)" stroke-width="1" visibility="hidden"/>';
    s += '<rect class="hit" x="' + pad.l + '" y="0" width="' + (W - pad.l - pad.r) + '" height="' + H + '" fill="transparent"/></svg><div class="tip" hidden></div>';
    el.innerHTML = s;
    var svg = el.querySelector("svg"), tip = el.querySelector(".tip"), xh = el.querySelector(".xh");
    function move(ev) {
      var r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width;
      var i = Math.round((px - pad.l) * (n - 1) / (W - pad.l - pad.r)); i = Math.max(0, Math.min(n - 1, i));
      xh.setAttribute("x1", X(i)); xh.setAttribute("x2", X(i)); xh.setAttribute("visibility", "visible");
      var rows = cfg.series.map(function (se) {
        var p = se.pts.filter(function (q) { return q[0] === i; })[0];
        return p && p[1] !== null ? '<div><i style="background:' + se.color + '"></i>' + esc(se.name) + " <b>" + fmtV(p[1], cfg.ref) + "</b></div>" : "";
      }).join("") + (cfg.bands || []).map(function (b) {
        var a = b.lo.filter(function (q) { return q[0] === i; })[0], z = b.hi.filter(function (q) { return q[0] === i; })[0];
        return a && z && a[1] !== z[1] ? '<div><i style="background:' + b.color + ";opacity:" + Math.min(1, 2 * b.opacity) + '"></i>' + esc(b.name) + " <b>" + fmtV(a[1], cfg.ref) + " to " + fmtV(z[1], cfg.ref) + "</b></div>" : "";
      }).join("");
      if (!rows) { tip.hidden = true; return; }
      tip.innerHTML = '<div class="tt">' + esc(cfg.xfmt(cfg.labels[i])) + "</div>" + rows;
      tip.hidden = false;
      var left = X(i) * r.width / W; tip.style.left = Math.min(left + 12, r.width - tip.offsetWidth - 4) + "px"; tip.style.top = "8px";
    }
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerleave", function () { tip.hidden = true; xh.setAttribute("visibility", "hidden"); });
  }

  function legend(items) {
    return items.map(function (it) { return '<span class="lg"><i style="background:' + it.color + (it.dash ? ";background:repeating-linear-gradient(90deg," + it.color + " 0 5px,transparent 5px 8px)" : "") + (it.block ? ";height:10px" : "") + '"></i>' + esc(it.name) + "</span>"; }).join("");
  }

  // ---- render -------------------------------------------------------------
  var COLS = [
    { k: "MASE", t: "MASE", tip: "Mean absolute scaled error: MAE divided by the in-sample error of a seasonal-naive forecast. Ranks the table, in the same order as MAE." },
    { k: "MAE", t: "MAE", tip: "Mean absolute error, in the series' own units." },
    { k: "RMSE", t: "RMSE", tip: "Root mean squared error. Punishes big misses more than MAE." },
    { k: "MSE", t: "MSE", tip: "Mean squared error (RMSE squared)." },
    { k: "MAPE", t: "MAPE %", tip: "Mean absolute percentage error. Undefined if any actual is zero; favours under-forecasts." },
    { k: "sMAPE", t: "sMAPE %", tip: "Symmetric MAPE: error divided by the average of actual and forecast." },
    { k: "ME", t: "Bias (ME)", tip: "Mean error, actual minus forecast. Positive = the method under-forecasts on average." }
  ];

  function paramText(p) {
    if (!p) return "";
    var sym = { alpha: "α", beta: "β", gamma: "γ", phi: "φ", slope: "slope", theta: "θ", Theta: "Θ", lambda: "λ", trees: "trees" };
    return Object.keys(p).map(function (k) { return sym[k] + " " + (k === "slope" ? fmtV(p[k]) : Number.isInteger(p[k]) ? String(p[k]) : p[k].toFixed(2)); }).join(", ");
  }

  // ---- background fitting --------------------------------------------------
  // Fitting every method at every origin is the slow part. It runs in a Web Worker started from
  // the engine source inlined in this page (worker.js), so the page stays responsive and shows
  // progress; where workers are unavailable it runs on the page itself. Each series + seasonality
  // is fitted once and every horizon/window choice is scored from it. Two stages: first twice the
  // backtest window (enough for the table and the test of the choice), then older origins for the
  // forecast ranges, while the results are already on screen.
  var fitter = (function () {
    var w = null, useWorker = typeof Worker !== "undefined" && typeof Blob !== "undefined", seq = 0, cur = null;
    function start() {
      try {
        var src = $("fc-engine").textContent + "\n" + $("fc-worker").textContent;
        var wk = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
        wk.onmessage = function (ev) {
          var d = ev.data;
          if (!cur || d.job !== cur.id) return;
          if (d.fc || d.error) { var c = cur; cur = null; c.done(d); }
          else if (cur.progress) cur.progress(d.done / d.total);
        };
        wk.onerror = function (ev) { // the worker could not start (for example, blocked by the browser): fit on the page
          if (ev && ev.preventDefault) ev.preventDefault();
          useWorker = false; wk.terminate(); w = null;
          if (cur) local(cur);
        };
        return wk;
      } catch (e) { useWorker = false; return null; }
    }
    function local(job) {
      setTimeout(function () {
        if (cur !== job) return;
        var r;
        try { r = { fc: E.fitRange(job.q.y, job.q.m, job.q.lo, job.q.hi), lo: job.q.lo, fut: job.q.fut ? E.futures(job.q.y, job.q.m) : null }; }
        catch (e) { r = { error: e.message }; }
        if (cur !== job) return;
        document.documentElement.setAttribute("data-fit", "page");
        cur = null; job.done(r);
      }, 30);
    }
    return {
      // job: { key, stage, q: { y, m, lo, hi, fut }, progress(frac), done(result) }
      run: function (job) {
        if (cur && w) { w.terminate(); w = null; } // a newer request replaces the one running
        job.id = ++seq; cur = job;
        if (useWorker && !w) w = start();
        if (w) { var q = job.q; w.postMessage({ job: job.id, y: q.y, m: q.m, lo: q.lo, hi: q.hi, fut: q.fut }); }
        else local(job);
        document.documentElement.setAttribute("data-fit", w ? "worker" : "page"); // for the page tests
      },
      busy: function () { return cur; }
    };
  })();

  var cache = {};
  function keyOf(s) { return s.key + "|" + (s.uid || s.name) + "|" + state.m; }
  function run() {
    var s = current(), key = keyOf(s), err = $("err"), P = cache[key];
    unitLabels(s);
    err.hidden = true;
    if (!P) {
      try { P = cache[key] = E.skeleton(s.values, state.m, s.skip || []); }
      catch (e) { $("busy").hidden = true; err.textContent = e.message; err.hidden = false; return; }
    }
    var need = 2 * Math.max(state.test, state.testPref || 0), lo = Math.min(E.loFor(P, need), P.lo);
    if (lo >= P.lo && P.fut) { $("busy").hidden = true; render(s, P); return calibrate(s, P, key); }
    var job = fitter.busy();
    if (job && job.key === key && job.q.lo <= lo && (P.fut || job.q.fut)) { job.main = true; return showBusy(job); } // already fitting what is needed
    job = { key: key, main: true, q: { y: P.y, m: P.m, lo: lo, hi: P.lo, fut: !P.fut } };
    job.label = P.fut ? "Fitting older origins to test the choice" : "Fitting every method at each backtest origin";
    job.progress = function (f) { job.frac = f; showBusy(job); };
    job.done = function (r) { fitted(s, P, key, job, r); };
    fitter.run(job); showBusy(job);
  }
  function showBusy(job) {
    if (job.main) { $("busy").innerHTML = "<b>" + esc(job.label || "Fitting older origins") + "… " + Math.round(100 * (job.frac || 0)) + "%</b>"; $("busy").hidden = false; }
    else rangeBusy(job);
  }
  function fitted(s, P, key, job, r) {
    if (r.error) {
      if (job.main) { $("busy").hidden = true; $("err").textContent = r.error; $("err").hidden = false; }
      else { P.calFailed = r.error; if (key === keyOf(current())) render(s, P); }
      return;
    }
    E.merge(P, r.fc, r.lo);
    if (r.fut) P.fut = r.fut;
    if (key !== keyOf(current())) return; // the user has moved on; the fits stay cached
    if (job.main) $("busy").hidden = true;
    run();
  }
  // Older origins for the forecast ranges: errors from as far back as the data allows, up to
  // CAL per step ahead, plus enough before the backtest window to check the ranges there.
  // The check at the oldest backtest origin needs CAL errors before it, and each of those needs the
  // backtest window before it to re-pick the pool: 2 x window + h + CAL - 1 origins in all.
  function calOrigins() { return 2 * state.test + state.h + E.CAL - 1; }
  function calLo(P) { return Math.max(E.minTrain(P.m), P.y.length - calOrigins()); }
  function calibrate(s, P, key) {
    var lo = calLo(P);
    if (lo >= P.lo || P.calFailed) return;
    var job = fitter.busy();
    if (job && job.key === key) return; // already running
    job = { key: key, main: false, q: { y: P.y, m: P.m, lo: lo, hi: P.lo, fut: false } };
    job.progress = function (f) { job.frac = f; showBusy(job); };
    job.done = function (r) { fitted(s, P, key, job, r); };
    fitter.run(job); showBusy(job);
  }
  function rangeBusy(job) {
    var el = $("rbusy"); if (!el) return;
    el.textContent = "Building the range from older tests… " + Math.round(100 * (job.frac || 0)) + "%"; el.hidden = false;
  }
  function moreNeeded(P, need) { return Math.max(P.y.length - need, E.minTrain(P.m)) < P.lo; }

  // The page's advice, decided in a fixed order: the top-3 pool by default; the single best
  // method only if, re-picked at each origin, it beat the pool by a margin unlikely to be luck;
  // naive if the chosen approach did not beat naive when tested the way it would be used.
  function decide(res, nv) {
    if (!res.pool) return { kind: res.hindsight.metrics.MAE < nv.metrics.MAE ? "pool" : "naive", honest: false, row: res.hindsight };
    var t = E.dmTest(res.pick.loss, res.pool.loss), kind = isFinite(t.p) && t.p < 0.05 && t.mean < 0 ? "pick" : "pool";
    var row = kind === "pick" ? res.pick : res.pool;
    return { kind: row.metrics.MAE < nv.metrics.MAE ? kind : "naive", tried: kind, honest: true, row: row, pickVsPool: t };
  }
  function relPct(a, b) { return 100 * (a / b - 1); }
  function relText(v) { return !isFinite(v) ? "n/a" : (v < 0 ? "−" : v > 0 ? "+" : "") + fmt(Math.abs(v), 1) + "%"; }
  function pf(p) { return !isFinite(p) ? "not testable" : p < 0.001 ? "p < 0.001" : "p = " + fmt(p, 3); }
  function nameList(names) { names = names.map(function (x) { return "<b>" + esc(x) + "</b>"; }); return names.length < 2 ? names.join("") : names.slice(0, -1).join(", ") + " and " + names[names.length - 1]; }

  // The forecast each approach made k steps before each date of the backtest window. "pool" and
  // "pick" are re-chosen at each origin exactly as in the backtest (E.picksFor), so the dots for
  // k = h are the forecasts the table scores. Dates whose origin is not fitted yet are left out.
  function pastDots(P, id, k) {
    var n = P.y.length, sk = P.skip || {}, rep = id === "pool" || id === "pick", out = [], picks = {};
    var T0 = Math.max(n - state.test - k + 1, P.lo), T1 = n - k, Tp = Math.max(T0, P.lo + state.test);
    if (T0 > T1) return out;
    if (rep && Tp <= T1) picks = E.picksFor(P, state.h, state.test, Tp, T1);
    // too short to re-pick (no tested pool): the methods picked today, as the table shows them
    var fixed = id === "pick" ? [last.ranked[0].id] : last.res.members;
    for (var T = T0; T <= T1; T++) {
      var t = T + k - 1; if (sk[t]) continue;
      var ids = !rep ? [id] : picks[T] ? (id === "pick" ? [picks[T][0]] : picks[T]) : last.res.pool ? null : fixed;
      if (!ids) continue; // older origin not fitted yet
      out.push([t, ids.reduce(function (a, m) { return a + P.fc[m][T][k - 1]; }, 0) / ids.length]);
    }
    return out;
  }
  // A sudden move: the recommended forecast's biggest miss one step ahead in the last few dates is
  // bigger than any earlier miss in the backtest window. Every method lags such a move, and a range
  // built from calmer errors understates the risk while it lasts (Barber et al., 2023).
  function jumpNote(s, P, pd) {
    var el = $("jump"), y = P.y, L = Math.min(3, Math.max(1, Math.floor(pd.length / 8)));
    el.hidden = true;
    if (state.dots !== "1" && state.h > 1) pd = pastDots(P, last.dec.kind === "pool" ? "pool" : last.dec.kind === "pick" ? "pick" : "naive", 1);
    if (pd.length < 10) return;
    var e = pd.map(function (q) { return Math.abs(y[q[0]] - q[1]); }), before = Math.max.apply(null, e.slice(0, -L)), recent = Math.max.apply(null, e.slice(-L));
    if (!(recent > before)) return;
    el.innerHTML = "The last few " + esc(many(s)) + " moved more than at any point in the backtest window. Every method here lags a sudden move like this, and the range is built from calmer times, so expect it to be too narrow until things settle.";
    el.hidden = false;
  }
  function headline(s, dec, prim, poolNames, rows, ref, ready) {
    var H = state.h, r = rows[H - 1], u = s.short ? " " + esc(s.short) : "", when = esc(label(futureDates(s.dates, H, s)[H - 1]));
    var out = "Plan on <b>" + fmtV(prim.future[H - 1], ref) + u + "</b> for " + when + (H > 1 ? ", " + H + " " + esc(many(s)) + " ahead" : "") + ".";
    var rg = last && last.rg, c = rg && rg.nCheck >= FEW ? rg.cover[0.8] : NaN, bnd = "<b>" + fmtV(r ? r.lo[MAIN] : 0, ref) + " to " + fmtV(r ? r.hi[MAIN] : 0, ref) + "</b>" + u;
    if (r && c < 0.7) out += " The 80% range is " + bnd + ", but in past tests ranges like it held only " + Math.round(10 * c) + " times in 10, so allow for more.";
    else if (r) out += " 8 times in 10 it should land between " + bnd.replace(" to ", " and ") + ".";
    else if (!ready) out += " The range is still being built.";
    var from = dec.kind === "pool" ? "the average of " + nameList(poolNames) + ", the three methods that held up best"
      : dec.kind === "pick" ? "<b>" + esc(prim.name) + "</b>, which beat the average of the top three on this series"
      : "the latest value. None of the methods beat it when tested on this series";
    return out + '<div class="sub">Forecast from ' + from + ".</div>";
  }

  function render(s, P) {
    var err = $("err"), WS = E.WINDOWS;
    // a window must be at least twice the horizon, so every step ahead is scored at least h+1 times
    Array.prototype.forEach.call($("h").options, function (o) { o.disabled = 2 * +o.value > P.W; });
    if (2 * state.h > P.W) { state.h = [12, 6, 3, 1].filter(function (v) { return 2 * v <= P.W; })[0]; $("h").value = String(state.h); }
    if (!state.testPref) state.testPref = state.test;
    var ok = WS.filter(function (w) { return w <= P.W && w >= 2 * state.h; });
    state.test = ok.filter(function (w) { return w <= state.testPref; }).pop() || ok[0];
    Array.prototype.forEach.call($("test").options, function (o) { o.disabled = ok.indexOf(+o.value) < 0; });
    $("test").value = String(state.test);
    if (moreNeeded(P, 2 * state.test)) return run();
    var meths = P.meths, res;
    try { res = E.score(P, { h: state.h, test: state.test }); }
    catch (e) { err.textContent = e.message; err.hidden = false; return; }
    var ranked = E.rank(relabel(res.results, s)), byId = {};
    res.results.forEach(function (r) { byId[r.id] = r; });
    var nv = byId.naive, sn = byId.snaive, best = ranked[0], dec = decide(res, nv);
    var poolNames = res.members.map(function (id) { return byId[id].name; });
    // primary series on the page = what the page recommends
    var prim = dec.kind === "naive" ? { id: "naive", name: nv.name, r: nv, future: nv.future }
      : dec.kind === "pick" ? { id: best.id, name: best.name, r: res.pick, future: best.future }
      : { id: "pool", name: "Top-3 pool", r: dec.row, future: (res.pool || res.hindsight).future };
    var ref = s.values[s.values.length - 1], H = state.h;
    // forecast ranges, once the older origins they need are fitted
    var rg = null, calReady = P.lo <= calLo(P) || !!P.calFailed;
    if (calReady && !P.calFailed) rg = E.ranges(P, { h: H, test: state.test, kind: dec.kind, levels: LEVELS });
    var rows = prim.future.slice(0, H).map(function (f, i) {
      var b = rg && rg.future[i];
      var fl = rg && rg.floor === 0 ? 0 : -Infinity, clip = function (v) { return Math.max(v, fl); };
      return b ? { k: i + 1, f: f, n: b.n, p50: clip(f + b.p50), ok: b.ok, lo: b.lo.map(function (q) { return clip(f + q); }), hi: b.hi.map(function (q) { return clip(f + q); }) } : null;
    });
    last = { s: s, res: res, ranked: ranked, byId: byId, dec: dec, prim: prim, P: P, rg: rg, rows: rows };

    // tag, the answer, and the reasons behind it
    $("tag").innerHTML = s.sample ? '<span class="badge">SAMPLE DATA · synthetic, for demonstration</span>' : "";
    var ev = dec.kind === "naive" ? dec.row : prim.r;
    $("headline").innerHTML = headline(s, dec, prim, poolNames, rows, ref, calReady);
    $("kpis").innerHTML =
      kpi("Forecast, " + label(futureDates(s.dates, H, s)[H - 1]), fmtV(prim.future[H - 1], ref) + (s.short ? " " + s.short : ""), H + " " + (H > 1 ? many(s) : one(s)) + " ahead") +
      rangeKpi(s, rg, rows, ref, calReady) +
      kpi(dec.kind === "naive" ? (dec.tried === "pick" ? "Best method vs naive" : "Top-3 pool vs naive") : "Error vs naive", relText(relPct(ev.metrics.MAE, nv.metrics.MAE)),
        dec.honest ? "average miss, tested on the last " + state.test + " " + many(s) : "average miss, on the scores it was picked on");

    $("rec").innerHTML = recommend(s, res, ranked, byId, dec, prim, poolNames, ref);
    rangeCard(s, P, dec, prim, rg, rows, ref);
    honestTable(s, res, byId, best);

    // compare picker
    if (state.compare === prim.id || !byId[state.compare]) state.compare = prim.id === "naive" ? (best.id === "naive" ? ranked[1].id : best.id) : "naive";
    $("cmp").innerHTML = meths.filter(function (d) { return d.id !== prim.id; }).map(function (d) {
      return '<option value="' + d.id + '"' + (d.id === state.compare ? " selected" : "") + ">" + esc(displayName(d.id, d.name, s)) + "</option>";
    }).join("");
    var cmp = byId[state.compare];

    // main chart
    var n = s.values.length, fut = futureDates(s.dates, H, s), labels = s.dates.concat(fut);
    var actual = s.values.map(function (v, i) { return [i, v]; });
    // recent view: the backtest window plus as much history again (at least 60 periods), so the
    // forecast and its range are readable; "All history" shows everything
    var v0 = state.view === "all" ? 0 : Math.max(0, Math.min(res.first - state.test, n - 60));
    // past forecasts: by default the one made 1 step before each date in the backtest window, so
    // every date has one; or the one made h steps before, the horizon the table scores
    var dk = state.dots === "h" && H > 1 ? H : 1;
    $("dots").options[1].textContent = "Made " + H + " " + (H > 1 ? many(s) : one(s)) + " before";
    $("dots").options[1].disabled = H === 1; $("dots").value = dk === 1 ? "1" : "h";
    var primId = dec.kind === "pool" ? "pool" : dec.kind === "pick" ? "pick" : "naive";
    var pd = pastDots(P, primId, dk), cd = pastDots(P, cmp.id, dk);
    function fu(f) { return [[n - 1, s.values[n - 1]]].concat(f.slice(0, H).map(function (v, i) { return [n + i, v]; })); }
    var C1 = "var(--s1)", C2 = "var(--s2)", CA = "var(--text)", hs1 = dk === 1 ? "1 step" : dk + " steps";
    var series = [
      { name: "Actual", color: CA, pts: actual },
      { name: prim.name + " (made " + hs1 + " before)", color: C1, pts: pd, dots: true },
      { name: prim.name + " (forecast)", color: C1, pts: fu(prim.future), dots: H === 1 },
      { name: cmp.name + " (made " + hs1 + " before)", color: C2, pts: cd, dots: true, dash: true },
      { name: cmp.name + " (forecast)", color: C2, pts: fu(cmp.future), dash: true, dots: H === 1 }
    ];
    var bands = [], lgs = [{ name: "Actual", color: CA }, { name: prim.name + " (recommended)", color: C1 }];
    if (rows.every(Boolean)) LEVELS.map(function (L, i) { return i; }).reverse().forEach(function (li) {
      if (!rows.every(function (r) { return r.ok[li]; })) return;
      bands.push({ name: pctL(LEVELS[li]) + " range", color: C1, opacity: [0.24, 0.16, 0.09][li],
        lo: [[n - 1, s.values[n - 1]]].concat(rows.map(function (r, i) { return [n + i, r.lo[li]]; })),
        hi: [[n - 1, s.values[n - 1]]].concat(rows.map(function (r, i) { return [n + i, r.hi[li]]; })) });
    });
    bands.slice().reverse().forEach(function (b) { lgs.push({ name: b.name, color: "rgba(76,154,255," + (0.15 + b.opacity * 2).toFixed(2) + ")", block: true }); });
    lgs.push({ name: cmp.name, color: C2, dash: true });
    $("lg1").innerHTML = legend(lgs);
    function cut(pts) { return pts.filter(function (p) { return p[0] >= v0; }).map(function (p) { return [p[0] - v0, p[1]]; }); }
    series.forEach(function (se) { se.pts = cut(se.pts); });
    bands.forEach(function (b) { b.lo = cut(b.lo); b.hi = cut(b.hi); });
    var u1 = one(s), um = many(s);
    $("ch1h").textContent = (last.res.pool || dec.kind === "naive" ? "" : "This series is too short to re-pick the top three at each past point, so the dots use today's three. ") + "Dots in the shaded window are what each method forecast " + (dk === 1 ? "one " + u1 : dk + " " + um) + " before that date, using only the data it had then." +
      (dk > 1 ? " They trail sharp moves by " + dk + " " + um + "." : "") + " After the last actual: the forecast and the range to plan around.";
    jumpNote(s, P, pd);
    lineChart($("ch1"), { labels: labels.slice(v0), series: series, bands: bands, xfmt: label, ref: ref, band: [Math.max(0, res.first - 0.5 - v0), n - 1 - v0], bandLabel: "Backtest window",
      aria: "Actual values with backtest and " + H + "-" + one(s) + " forecasts for " + prim.name + " and " + cmp.name + (bands.length ? ", with forecast ranges" : ""), height: 320 });

    // horizon chart
    if (state.h > 1) {
      $("hz").hidden = false;
      var hl = []; for (var k = 1; k <= state.h; k++) hl.push(k);
      var hs = [{ name: prim.name, color: C1, pts: prim.r.maeByH.map(function (v, i) { return [i, v]; }), dots: true },
        { name: cmp.name, color: C2, pts: cmp.maeByH.map(function (v, i) { return [i, v]; }), dots: true, dash: true }];
      $("lg2").innerHTML = legend([{ name: prim.name, color: C1 }, { name: cmp.name, color: C2, dash: true }]);
      lineChart($("ch2"), { labels: hl, series: hs, xfmt: function (k) { return k + " ahead"; }, ref: ref, aria: "MAE by forecast horizon", height: 220, zero: true });
    } else $("hz").hidden = true;

    table(ranked);
    $("ch1t").textContent = "Actuals, backtest and " + (H === 1 ? "next-" + one(s) : H + "-" + one(s)) + " forecast";
    $("meta").innerHTML = esc(s.name) + (s.unit ? " · " + esc(s.unit) : "") + " · " + n + " " + many(s) + ", " + label(s.dates[0]) + " to " + label(s.dates[n - 1]) + " · Source: " + (s.sourceHtml || esc(s.source));
  }

  // Method names and notes that mention months are reworded for other time units.
  function displayName(id, name, s) { return id === "ma3" && one(s) !== "month" ? "3-" + one(s) + " moving average" : name; }
  function relabel(results, s) {
    results.forEach(function (r) {
      r.name = displayName(r.id, r.name, s);
      if (one(s) === "month") return;
      if (r.id === "snaive") r.note = "Next value = the value one seasonal cycle earlier.";
      if (r.id === "ma3") r.note = "Flat forecast at the average of the last 3 " + many(s) + ".";
    });
    return results;
  }

  function kpi(t, v, sub) { return '<div class="kpi"><div class="kt">' + esc(t) + '</div><div class="kv">' + esc(v) + '</div><div class="ks">' + esc(sub) + "</div></div>"; }

  // ---- forecast ranges --------------------------------------------------------
  var LEVELS = [0.5, 0.8, 0.95], MAIN = 1; // MAIN: index of the planning range (80%)
  var FEW = 20; // fewer checked forecasts than this: report the count, not a verdict (binomial s.e. at 80% is about 9 points at 20)
  function pctL(L) { return Math.round(100 * L) + "%"; }
  function pct(x) { return isFinite(x) ? Math.round(100 * x) + "%" : "n/a"; }
  function rangeKpi(s, rg, rows, ref, ready) {
    var H = state.h, r = rows[H - 1], when = label(futureDates(s.dates, H, s)[H - 1]);
    if (!ready) return kpi("80% range, " + when, "…", "building from older tests");
    if (!r) return kpi("80% range, " + when, "n/a", "not enough history");
    return kpi("80% range, " + when, fmtV(r.lo[MAIN], ref) + " to " + fmtV(r.hi[MAIN], ref), !isFinite(rg.cover[0.8]) ? "not yet checked: too little history" : rg.nCheck < FEW ? "held " + Math.round(rg.cover[0.8] * rg.nCheck) + " of " + rg.nCheck + " times in past tests" : "held " + pct(rg.cover[0.8]) + " of the time in past tests");
  }
  function rangeCard(s, P, dec, prim, rg, rows, ref) {
    var el = $("ranges"), ck = $("rcheck"), H = state.h, fd = futureDates(s.dates, H, s), job = fitter.busy();
    var hz = H + " " + (H > 1 ? many(s) : one(s)) + " ahead";
    $("monthly").querySelector("summary").textContent = H > 1 ? "Every " + one(s) + " to " + label(fd[H - 1]) : "Full range";
    $("rbusy").hidden = true;
    if (P.calFailed) { el.innerHTML = ck.innerHTML = '<p class="hint" style="margin:0">The range could not be built: ' + esc(P.calFailed) + "</p>"; return; }
    if (!rg) { el.innerHTML = ck.innerHTML = ""; if (job && job.key === keyOf(s) && !job.main) rangeBusy(job); else { $("rbusy").textContent = "Building the range from older tests…"; $("rbusy").hidden = false; } return; }
    var r = rows[H - 1], nmax = rows.reduce(function (a, x) { return x ? Math.max(a, x.n) : a; }, 0);
    if (!r) {
      // how many step-h errors a window w would give: one per origin from (first fitted + w) to n - h
      var n = s.values.length, lo0 = Math.max(E.minTrain(P.m), P.lo), have = rg.future[H - 1] ? rg.future[H - 1].n : Math.max(0, n - H - rg.start + 1);
      var fit = E.WINDOWS.filter(function (w) { return w >= 2 * H && w <= P.W && w < state.test && n - H - (lo0 + w) + 1 >= E.MINCAL; }).pop();
      el.innerHTML = ck.innerHTML = '<p style="margin:0">Not enough history for a tested range ' + esc(hz) + ": it needs at least " + E.MINCAL + " past forecasts made that far ahead, and there are " + have + "." +
        (fit ? " A backtest window of " + fit + " " + esc(many(s)) + " would give enough." : " A shorter horizon may allow one.") + "</p>";
      return;
    }
    var who = dec.kind === "naive" ? "naive" : dec.kind === "pick" ? esc(prim.name) : "the top-3 pool";
    var c = rg.cover[0.8], ab = rg.above[0.8], bl = rg.below[0.8], html = '<p style="margin:0 0 8px">The range comes from ' + who + "'s last " + r.n + " misses " + esc(hz) + ".";
    if (rg.nCheck) {
      var few = rg.nCheck < FEW;
      html += " Rebuilt at each past point in the backtest window from only the misses known then, the 80% range held " + Math.round(c * rg.nCheck) + " of " + rg.nCheck + " times (" + pct(c) + ")." +
        (few ? " That is too few to judge." : c < 0.7 ? " That is less often than it should, so expect more surprises than the range suggests." : c > 0.9 ? " That is more often than it should, so the range is on the cautious side." : "") + "</p>";
      if (!few) html += '<p style="margin:0 0 8px">For a budget or a price cap, treat the top end as the cautious case: the actual came in above it ' + pct(ab) + " of the time and below the bottom " + pct(bl) + " (10% each is the target).</p>";
    } else html += " There is not enough history to check it.</p>";
    ck.innerHTML = html;
    var show = LEVELS.map(function (L, li) { return rows.every(function (x) { return !x || x.ok[li]; }); });
    var t = '<div class="tblwrap"><table><thead><tr><th class="l">' + esc(one(s).charAt(0).toUpperCase() + one(s).slice(1)) + "</th><th>Forecast</th>" +
      LEVELS.map(function (L, li) { return show[li] ? "<th>" + pctL(L) + " range</th>" : ""; }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (x, i) {
      t += '<tr><td class="l">' + esc(label(fd[i])) + "</td><td>" + fmtV(prim.future[i], ref) + "</td>" +
        LEVELS.map(function (L, li) { return show[li] ? "<td>" + (x ? fmtV(x.lo[li], ref) + " to " + fmtV(x.hi[li], ref) : "n/a") + "</td>" : ""; }).join("") + "</tr>";
    });
    t += "</tbody></table></div>";
    if (!show[2] && nmax) t += '<div class="hint">A 95% range needs at least 39 past forecasts per step, so it is not shown.</div>';
    el.innerHTML = t;
  }

  function recommend(s, res, ranked, byId, dec, prim, poolNames, ref) {
    var best = ranked[0], nv = byId.naive, u1 = one(s), unit = s.short ? " " + esc(s.short) : "";
    var hz = state.h + " " + (state.h > 1 ? many(s) : one(s)) + " ahead", out = "<ul>";
    var honestP = res.pool ? E.holm([E.dmTest(res.pool.loss, nv.loss).p, E.dmTest(res.pick.loss, nv.loss).p]) : null;
    if (dec.kind === "pool") out += "<li><b>Average of the top three</b> (" + nameList(poolNames) + "). Averaging a few strong methods is safer than betting on one, because the #1 spot is partly luck.</li>";
    else if (dec.kind === "pick") out += "<li><b>" + esc(best.name) + " alone.</b> Picking the single best method each " + u1 + " beat the top-three average on this series by more than luck would explain (" + pf(dec.pickVsPool.p) + ").</li>";
    var r = dec.row, g = relPct(r.metrics.MAE, nv.metrics.MAE), who = dec.kind === "naive" ? (dec.tried === "pick" ? "the best single method" : "the top-three average") : dec.kind === "pick" ? "it" : "the average";
    if (!dec.honest) {
      out += "<li>The series is too short to test the choice properly (" + res.needN + " " + many(s) + " needed with a " + state.test + "-" + u1 + " window, " + s.values.length + " here), so these numbers are a little flattering. " +
        "On the window used to choose, " + who + " missed by " + fmtV(r.metrics.MAE, ref) + unit + " on average " + hz + ", " + fmt(Math.abs(g), 1) + "% " + (g <= 0 ? "less" : "more") + " than naive." +
        (dec.kind === "naive" ? " That is no better than naive, so plan on the latest value." : "") + " A shorter backtest window may allow the full test.</li>";
    } else {
      var pAdj = honestP[dec.tried === "pick" ? 1 : 0];
      if (dec.kind === "naive") {
        out += "<li><b>Plan on the latest value.</b> Picked again each " + u1 + " from only what was known then, " + who + " missed " + fmt(Math.abs(g), 1) + "% " + (g <= 0 ? "less" : "more") + " than naive " + hz +
          ", which is no real gain. On this series, effort is better spent on contract terms or hedging than on a model.</li>";
      } else {
        out += "<li>Picked again each " + u1 + " from only what was known then, " + who + " missed by " + fmtV(r.metrics.MAE, ref) + unit + " on average " + hz + ", " + fmt(Math.abs(g), 1) + "% less than naive. " +
          (!isFinite(pAdj) ? "Whether that edge is real cannot be tested here." : pAdj < 0.05 ? "That edge is unlikely to be luck (" + pf(pAdj) + ")." : "The test is too short to tell if that edge is real (" + pf(pAdj) + "), so naive is a fair fallback.") + "</li>";
        if (g > -5) out += "<li>An edge under 5% is small. Treat the series as close to a random walk and put effort into hedging or contract terms.</li>";
      }
      out += "<li>The table's #1, " + esc(best.name) + ", looks better (average miss " + fmtV(best.metrics.MAE, ref) + ") because it is scored on the same misses it was picked on. Picked fresh each " + u1 + ", the best single method missed by " +
        fmtV(res.pick.metrics.MAE, ref) + " and the top-three average by " + fmtV(res.pool.metrics.MAE, ref) + ".</li>";
    }
    out += tiedText(ranked, res, s);
    var bias = r.metrics.ME, rel = Math.abs(bias) / r.metrics.MAE;
    if (dec.kind !== "naive" && rel > 0.5) out += "<li>It tends to " + (bias > 0 ? "under" : "over") + "-forecast (by " + fmtV(Math.abs(bias), ref) + unit + " on average), so " + (bias > 0 ? "budgets and safety stock set from it will run short." : "budgets set from it will be padded.") + "</li>";
    var winners = {};
    ["RMSE", "MAPE", "sMAPE"].forEach(function (k) {
      var w = ranked.filter(function (x) { return x.metrics[k] !== null; }).sort(function (a, b) { return a.metrics[k] - b.metrics[k]; })[0];
      if (w && w.id !== best.id) (winners[w.name] = winners[w.name] || []).push(k);
    });
    var rw = Object.keys(winners).filter(function (n) { return winners[n].indexOf("RMSE") >= 0; })[0];
    if (rw) out += "<li>If one big miss costs you more than several small ones, RMSE is the better yardstick, and it puts " + esc(rw) + " first (see More measures).</li>";
    return out + "</ul>";
  }

  // Methods not shown to be worse than the table's #1 (Diebold-Mariano, Holm-adjusted across
  // the table). The ranking among them is not reliable.
  function vsBest(ranked) {
    var best = ranked[0], others = ranked.slice(1), adj = E.holm(others.map(function (r) { return E.dmTest(r.loss, best.loss).p; })), o = {};
    others.forEach(function (r, i) { o[r.id] = adj[i]; });
    return o;
  }
  function tiedText(ranked, res, s) {
    var vb = last.vb = vsBest(ranked), best = ranked[0], others = ranked.slice(1);
    var worse = others.filter(function (r) { return vb[r.id] < 0.05; }).length, tied = others.length - worse;
    if (!tied) return "<li>Every other method did clearly worse than " + esc(best.name) + " here.</li>";
    return "<li>" + (worse ? tied + " of the other " + others.length + " methods are" : "All " + others.length + " other methods are") + " statistically tied with the #1 (only " + res.origins +
      " test points), so treat the table order as a rough guide.</li>";
  }

  // Testing the choice itself: each approach is re-picked at every past origin from the errors
  // known then, and scored on what happened next. The hindsight row is shown for contrast.
  function honestTable(s, res, byId, best) {
    var nv = byId.naive, sn = byId.snaive, el = $("honest");
    if (!res.pool) {
      el.innerHTML = '<p class="hint" style="margin:0">Needs at least ' + res.needN + " " + many(s) + " of history with a " + state.test + "-" + one(s) +
        " backtest window; this series has " + s.values.length + ". A shorter window may allow it.</p>";
      return;
    }
    var p = E.holm([E.dmTest(res.pool.loss, nv.loss).p, E.dmTest(res.pick.loss, nv.loss).p]);
    var rows = [
      { name: "Top-3 pool", note: "Average of the three best methods, picked again each time", r: res.pool, p: p[0], cls: "win" },
      { name: "Best single method", note: "The top method, picked again each time", r: res.pick, p: p[1] },
      { name: "Naive", note: "Benchmark: the latest value", r: nv, p: null }
    ];
    if (sn) rows.push({ name: "Seasonal naive", note: "Benchmark: the value one cycle earlier", r: sn, p: null });
    rows.push({ name: esc(best.name) + ", best in hindsight", note: "Scored on the window it was picked on, so this number is optimistic", r: best, p: null, cls: "dim" });
    var ref = s.values[s.values.length - 1];
    var h = '<table><thead><tr><th class="l">Approach</th><th title="Mean absolute error, in the series\' units">Average miss</th>' +
      '<th title="MAE relative to naive on the same forecasts (Davydenko &amp; Fildes, 2013)">vs naive</th>' + (sn ? '<th title="MAE relative to seasonal naive on the same forecasts">vs seasonal naive</th>' : "") +
      '<th title="Diebold-Mariano test against naive, fixed-b variance, Holm-adjusted over the two re-picked approaches">p vs naive</th></tr></thead><tbody>';
    rows.forEach(function (o) {
      var m = o.r.metrics, isNv = o.r === nv;
      h += "<tr" + (o.cls ? ' class="' + o.cls + '"' : "") + '><td class="l"><b>' + o.name + '</b><div class="ref">' + esc(o.note) + "</div></td><td>" + fmt(m.MAE, digits(ref)) + "</td><td>" + (isNv ? "–" : relText(relPct(m.MAE, nv.metrics.MAE))) + "</td>" + (sn ? "<td>" + (o.r === sn ? "–" : relText(relPct(m.MAE, sn.metrics.MAE))) + "</td>" : "") +
        "<td>" + (o.p === null ? "–" : !isFinite(o.p) ? "n/a" : o.p < 0.05 ? "<b>" + (o.p < 0.001 ? "&lt;0.001" : fmt(o.p, 3)) + "</b>" : fmt(o.p, 3)) + "</td></tr>";
    });
    el.innerHTML = '<div class="tblwrap">' + h + "</tbody></table></div>";
  }

  function pvCells(ranked) { // Holm-adjusted across the table
    var nv = last.byId.naive, others = ranked.filter(function (r) { return r.id !== "naive"; });
    var tests = others.map(function (r) { return E.dmTest(r.loss, nv.loss); }), adj = E.holm(tests.map(function (t) { return t.p; })), o = {};
    others.forEach(function (r, i) {
      var p = adj[i], txt = !isFinite(p) ? "n/a" : p < 0.001 ? "<0.001" : fmt(p, 3);
      o[r.id] = isFinite(p) && p < 0.05 ? (tests[i].mean < 0 ? "<b>" + txt + " better</b>" : txt + " worse") : txt;
    });
    o.naive = "–";
    return o;
  }
  function table(ranked) {
    var rows = ranked.map(function (r, i) { return { r: r, rank: i + 1 }; });
    if (state.sort !== "rank") rows.sort(function (a, b) {
      var x = a.r.metrics[state.sort], y = b.r.metrics[state.sort];
      if (state.sort === "ME") { x = Math.abs(x); y = Math.abs(y); }
      if (x === null) return 1; if (y === null) return -1;
      return state.dir * (x - y);
    });
    var bestOf = {}, pv = pvCells(ranked), vb = last.vb || vsBest(ranked), pool = last.res.members, more = state.more, nvM = last.byId.naive.metrics.MAE;
    var cols = more ? COLS : [{ k: "MAE", t: "Average miss", tip: "Mean absolute error over the backtest window, in the series' own units (MAE)." }];
    $("tblh").textContent = more ? "Ranked by MASE (same order as MAE). These are the scores the ranking was made on, so the #1 is flattered. p-values: Diebold-Mariano test, fixed-b variance, Holm-adjusted across the table. ★ = best in column. Click a column to sort; hover a header for its definition."
      : "Ranked by average miss over the backtest window, scored on the same misses the ranking was made on, so the #1 looks a little better than it will do next. Click a column to sort.";
    cols.forEach(function (c) {
      var v = ranked.map(function (r) { var m = r.metrics[c.k]; return m === null ? Infinity : c.k === "ME" ? Math.abs(m) : m; });
      bestOf[c.k] = Math.min.apply(null, v);
    });
    var ref = last.s.values[last.s.values.length - 1];
    var h = '<table><thead><tr><th data-k="rank" class="l">#</th><th class="l">Method</th>' +
      cols.map(function (c) { return '<th data-k="' + c.k + '" title="' + esc(c.tip) + '">' + c.t + (state.sort === c.k ? (state.dir > 0 ? " ▲" : " ▼") : "") + "</th>"; }).join("") +
      (more ? '<th title="Diebold-Mariano test against naive (fixed-b variance), Holm-adjusted across the table. Below 0.05 = significantly different.">p vs naive</th>' +
        '<th title="Diebold-Mariano test against the #1 method, Holm-adjusted. Tied = not shown to be worse; with few origins the test only separates large, steady differences.">vs #1</th><th class="l">Fitted parameters</th>'
        : '<th title="Average miss compared with naive (the latest value) on the same dates">vs naive</th>') + "</tr></thead><tbody>";
    rows.forEach(function (o) {
      var r = o.r, m = r.metrics, p1 = vb[r.id];
      var v1 = o.rank === 1 ? "–" : !(p1 < 0.05) ? "tied" : "worse, " + (p1 < 0.001 ? "p<0.001" : "p " + fmt(p1, 3));
      h += '<tr' + (o.rank === 1 ? ' class="win"' : "") + '><td class="l">' + o.rank + '</td><td class="l"><b>' + esc(r.name) + "</b>" + (pool.indexOf(r.id) >= 0 ? ' <span class="pill">in top 3</span>' : "") + '<div class="ref">' + esc(r.note) + (more ? " " + esc(r.ref) : "") + "</div></td>" +
        cols.map(function (c) {
          var v = m[c.k], isBest = v !== null && (c.k === "ME" ? Math.abs(v) : v) === bestOf[c.k];
          var d = c.k === "MASE" ? 3 : (c.k === "MAPE" || c.k === "sMAPE") ? 2 : c.k === "MSE" ? digits(v) : digits(ref);
          return '<td data-m="' + c.k + '"' + (isBest && more ? ' class="best" title="Best in column"' : "") + ">" + (isBest && more ? "★ " : "") + fmt(v, d) + "</td>";
        }).join("") + (more ? "<td>" + pv[r.id] + "</td><td>" + v1 + '</td><td class="l pm">' + esc(paramText(r.params)) + "</td>" : "<td>" + (r.id === "naive" ? "–" : relText(relPct(m.MAE, nvM))) + "</td>") + "</tr>";
    });
    $("tbl").innerHTML = h + "</tbody></table>";
    Array.prototype.forEach.call($("tbl").querySelectorAll("th[data-k]"), function (th) {
      th.addEventListener("click", function () {
        var k = th.getAttribute("data-k");
        if (state.sort === k) state.dir = -state.dir; else { state.sort = k; state.dir = 1; }
        table(last.ranked);
      });
    });
  }

  // CSV (RFC 4180 quoting): every backtest forecast of every method and of the two re-picked
  // approaches; for the recommended approach, the 80% range (p10, p90) and middle (p50) as built at
  // each origin in the check; then the forecast rows from the end of the data with their ranges.
  function csvField(v) { var t = v === null || v === undefined ? "" : String(v); return /[",\r\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }
  function downloadCSV() {
    if (!last) return;
    var L = last, s = L.s, n = s.values.length, li = MAIN, lines = [["method", "origin_date", "steps_ahead", "target_date", "actual", "forecast", "error", "p10", "p50", "p90"].join(",")];
    var rows = L.res.results.map(function (r) { return { name: r.name, records: r.records, id: r.id }; });
    if (L.res.pool) rows.push({ name: "Top-3 pool (re-picked at each origin)", records: L.res.pool.records, id: "pool" }, { name: "Best single method (re-picked at each origin)", records: L.res.pick.records, id: "pick" });
    var recId = L.dec.kind, chk = {};
    if (L.rg) L.rg.check.forEach(function (c) { chk[c.T + "|" + c.k] = c; });
    rows.forEach(function (r) {
      var withRange = r.id === recId;
      r.records.forEach(function (q) {
        var c = withRange ? chk[q.origin + "|" + q.k] : null;
        lines.push([r.name + (withRange ? " (recommended)" : ""), s.dates[q.origin - 1], q.k, s.dates[q.idx], q.y, q.f, q.e, c ? c.lo[li] : "", c ? c.p50 : "", c ? c.hi[li] : ""].map(csvField).join(","));
      });
    });
    var fd = futureDates(s.dates, state.h, s);
    L.rows.forEach(function (x, i) {
      lines.push(["Forecast: " + L.prim.name + " (recommended)", s.dates[n - 1], i + 1, fd[i], "", L.prim.future[i], "", x ? x.lo[li] : "", x ? x.p50 : "", x ? x.hi[li] : ""].map(csvField).join(","));
    });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv" }));
    a.download = "forecast-" + String(s.key || "series").replace(/[^A-Za-z0-9_-]+/g, "-") + ".csv"; document.body.appendChild(a); a.click(); a.remove();
  }

  // ---- Industry Market Watch series ------------------------------------------
  var loaded = {}, byKey = {};
  MW.items.forEach(function (it) {
    byKey[it.k] = it;
    it.q = [it.n, it.id, it.u, it.p, it.ind.join(" "), (MW.groups.filter(function (g) { return g.k === it.g; })[0] || {}).label].join(" ").toLowerCase();
  });
  function opt(k, name, cur, dis) { return '<option value="' + esc(k) + '"' + (k === cur ? " selected" : "") + (dis ? " disabled" : "") + ">" + esc(name) + "</option>"; }
  function fillSeries() {
    var words = $("find").value.toLowerCase().split(/\s+/).filter(Boolean), cur = state.key;
    function hit(txt) { return words.every(function (w) { return txt.indexOf(w) >= 0; }); }
    var html = "", count = 0, curHit = !words.length;
    var ex = SERIES.filter(function (x) { return !words.length || hit(x.name.toLowerCase()); });
    if (ex.some(function (x) { return x.key === cur; })) curHit = true;
    if (ex.length) html += '<optgroup label="Example">' + ex.map(function (x) { return opt(x.key, x.name, cur); }).join("") + "</optgroup>";
    MW.groups.forEach(function (g) {
      var its = MW.items.filter(function (it) { return it.g === g.k; });
      count += its.filter(function (it) { return words.length && hit(it.q); }).length;
      its = its.filter(function (it) { return !words.length || hit(it.q); });
      if (its.some(function (it) { return it.k === cur; })) curHit = true;
      if (its.length) html += '<optgroup label="' + esc(g.label) + '">' + its.map(function (it) { return opt(it.k, it.n, cur); }).join("") + "</optgroup>";
    });
    html += '<optgroup label="Your data">' + opt("upload", state.upload ? "Uploaded: " + state.upload.name : "Uploaded file (use the button)", cur, !state.upload) + "</optgroup>";
    if (cur === "upload" && state.upload) curHit = true;
    if (!curHit) html = '<option value="" disabled selected>' + (count ? "Pick one of " + count + " matches" : "No matches") + "</option>" + html;
    $("series").innerHTML = html; if (curHit) $("series").value = cur;
    var fn = $("findn");
    fn.hidden = !words.length;
    fn.textContent = !words.length ? "" : count ? count + (count === 1 ? " match" : " matches") + " in the Series menu" : "No series match “" + $("find").value.trim() + "”";
  }
  function loadSeries(it) {
    if (it.k.indexOf("mw:") === 0) {
      return MK.monthly(it.id).then(function (c) {
        return { key: it.k, name: it.n, unit: it.u, short: it.s, sample: false, dates: c.dates, values: c.values, m: 12, c: c, it: it,
          skip: c.filled.map(function (d) { return c.dates.indexOf(d); }), filledLabels: c.filled.map(label) };
      });
    }
    return MK.spot(it.id).then(function (c) {
      var res = window.FCUpload.build([["Date", it.n]].concat(c.dates.map(function (d, i) { return [d, String(c.values[i])]; })), { prefilled: c.filled });
      var m = res.suggestedM, mNote = "";
      if (m > 1 && res.values.length < E.minTrain(m) + 12) { mNote = "A " + m + "-" + res.unitOne + " seasonal cycle needs more history than this, so seasonality is set to None."; m = 1; }
      else if (m > 1) mNote = "Seasonality is set to " + m + " (" + cycleName(m, res.unit) + "); change it above if you like.";
      return { key: it.k, name: it.n, unit: it.u, short: it.s, sample: false, dates: res.dates, values: res.values, future: res.future,
        unitOne: res.unitOne, unitMany: res.unitMany, m: m, c: c, it: it, mNote: mNote,
        skip: res.filledIdx, filledLabels: res.filledIdx.map(function (i) { return res.dates[i]; }) };
    });
  }
  function mwNote(s) {
    var it = s.it, c = s.c, n = s.values.length;
    var h = "<div class=\"upok\"><b>Loaded from Industry Market Watch</b> (refreshed daily): " + n.toLocaleString() + " " + esc(n === 1 ? one(s) : many(s)) +
      ", " + esc(label(s.dates[0])) + " to " + esc(label(s.dates[n - 1])) + ". Published by " + esc(it.p) +
      (it.k.indexOf("mw:") === 0 ? ", via FRED (" + esc(it.id) + ")" : "") + ".</div>";
    if (it.ind.length) h += '<div class="upinfo">Tracked for: ' + esc(it.ind.join(", ")) + ".</div>";
    if (it.avg) h += '<div class="upinfo">Published daily or weekly; shown as monthly averages.</div>';
    var fl = s.filledLabels || [];
    if (fl.length) h += '<div class="upwarn">⚠ ' + esc(fl.slice(0, 6).join(", ") + (fl.length > 6 ? ", …" : "")) + (fl.length > 1 ? " were" : " was") +
      " missing at the source and " + (fl.length > 1 ? "are" : "is") + " filled by a straight line between neighbouring values, as on Market Watch. Filled values help fit the methods but are not scored.</div>";
    if (s.mNote) h += '<div class="upinfo">' + esc(s.mNote) + "</div>";
    return h;
  }
  function sourceHtml(it) {
    return esc(it.p) + ' (<a href="' + esc(it.src) + '" target="_blank" rel="noopener">' + (it.k.indexOf("mw:") === 0 ? "FRED " + esc(it.id) : "source page") + "</a>), loaded from Industry Market Watch";
  }
  var reqId = 0;
  function choose(k) {
    var prev = state.key, err = $("err");
    err.hidden = true;
    if (k === "upload") {
      if (!state.upload) { $("series").value = prev; return; }
      state.key = k; setM(state.upload.m); $("mwnote").hidden = true; $("upnote").hidden = false; run(); return;
    }
    $("upnote").hidden = true;
    var it = byKey[k];
    if (!it) { state.key = k; setM(current().m || 12); $("mwnote").hidden = true; run(); return; }
    function show(s) { state.key = k; setM(s.m); $("mwnote").innerHTML = mwNote(s); $("mwnote").hidden = false; run(); }
    if (loaded[k]) return show(loaded[k]);
    var my = ++reqId;
    $("busy").innerHTML = "<b>Loading " + esc(it.n) + " from Industry Market Watch…</b>"; $("busy").hidden = false;
    loadSeries(it).then(function (s) {
      s.sourceHtml = sourceHtml(it);
      loaded[k] = s;
      if (my !== reqId) return;
      show(s);
    }).catch(function (er) {
      if (my !== reqId) return;
      $("busy").hidden = true;
      err.textContent = "Could not load “" + it.n + "” from Industry Market Watch (" + (er && er.message || "network error") + "). Check your connection and pick it again.";
      err.hidden = false;
      state.key = prev; $("series").value = prev;
    });
  }

  // ---- uploads -------------------------------------------------------------
  var uid = 0, MAXN = 2000;
  function setM(v) {
    var sel = $("m"), has = Array.prototype.some.call(sel.options, function (o) { return o.value === String(v); });
    sel.value = has ? String(v) : "custom";
    $("mcustom").hidden = has; $("mcustom").value = v;
    state.m = v;
  }
  function unitLabels(s) {
    var o1 = one(s), om = many(s);
    Array.prototype.forEach.call($("h").options, function (o) { o.textContent = o.value + " " + (o.value === "1" ? o1 : om); });
    Array.prototype.forEach.call($("test").options, function (o) { o.textContent = "Last " + o.value + " " + om; });
  }
  function applyUpload(res, fname, keepM) {
    var notes = res.notes.slice(), warns = res.warnings.slice(), vals = res.values, dates = res.dates;
    if (vals.length > MAXN) {
      notes.push("The file has " + vals.length.toLocaleString() + " rows; the most recent " + MAXN.toLocaleString() + " are used to keep the page fast.");
      vals = vals.slice(-MAXN); dates = dates.slice(-MAXN);
    }
    var s = { key: "upload", uid: ++uid, name: res.name || fname.replace(/\.[^.]+$/, ""), unit: "", short: "", sample: false,
      source: "your file (" + fname + "), read in your browser", dates: dates, values: vals, future: res.future,
      unitOne: res.unitOne, unitMany: res.unitMany, res: res, fname: fname, m: keepM && state.upload ? state.upload.m : res.suggestedM,
      skip: (res.filledIdx || []).map(function (i) { return i - (res.values.length - vals.length); }).filter(function (i) { return i >= 0; }) };
    var mNote = "";
    if (!keepM) {
      var n = vals.length, want = res.suggestedM;
      if (want > 1 && n < E.minTrain(want) + 12) {
        mNote = " A " + want + "-" + res.unitOne + " seasonal cycle needs at least " + (E.minTrain(want) + 12) + " " + res.unitMany + " of history, so seasonality is set to None.";
        s.m = 1;
      } else if (want > 1) mNote = " Seasonality is set to " + want + " (" + cycleName(want, res.unit) + "); change it above if your data cycles differently.";
      else mNote = res.unit === "year" ? " Yearly data has no seasonality, so it is set to None." : " Seasonality is set to None; pick a cycle above if your data has one.";
    }
    if (vals.length < 10) { $("busy").hidden = true; $("err").textContent = "Only " + vals.length + " usable rows were found; at least 10 are needed (more for seasonal methods)."; $("err").hidden = false; return; }
    state.upload = s; state.key = "upload";
    setM(s.m);
    $("mwnote").hidden = true; fillSeries();
    var range = dates[0] + " to " + dates[dates.length - 1];
    var h = '<div class="upok"><b>' + esc(fname) + ":</b> " + vals.length.toLocaleString() + " values" + (res.ms ? ", one per " + esc(res.unitOne) + ", " + esc(range) : "") +
      (res.name ? ", column “" + esc(res.name) + "”" : "") + "." + (keepM ? "" : esc(mNote)) + "</div>";
    notes.forEach(function (x) { h += '<div class="upinfo">' + esc(x) + "</div>"; });
    if (res.orderAmbiguous) warns.unshift("Your dates could be read as month/day or day/month. Read as " + (res.order === "MDY" ? "month/day (US)" : "day/month") + " (" + res.orderHow + "). Check below.");
    warns.forEach(function (x) { h += '<div class="upwarn">⚠ ' + esc(x) + "</div>"; });
    var pick = "";
    if (res.numericCols.length > 1) pick += '<label class="ctl">Value column<select id="upcol">' + res.numericCols.map(function (c) {
      return '<option value="' + c.c + '"' + (c.c === res.valueCol ? " selected" : "") + ">" + esc(c.label) + "</option>"; }).join("") + "</select></label>";
    if (res.decimalAsk) pick += '<label class="ctl">Decimal mark<select id="updec"><option value="comma"' + (res.decimalComma ? " selected" : "") + '>Comma (1.234,5)</option><option value="point"' + (res.decimalComma ? "" : " selected") + ">Point (1,234.5)</option></select></label>";
    if (res.order) pick += '<label class="ctl">Date order<select id="uporder"><option value="MDY"' + (res.order === "MDY" ? " selected" : "") + '>Month/day (US)</option><option value="DMY"' + (res.order === "DMY" ? " selected" : "") + ">Day/month</option></select></label>";
    if (pick) h += '<div class="controls" style="margin-top:8px">' + pick + "</div>";
    $("upnote").innerHTML = h; $("upnote").hidden = false;
    function rebuild() {
      try {
        var dc = $("updec") ? $("updec").value === "comma" : res.decimalComma;
        var r2 = window.FCUpload.build(res.table, { valueCol: $("upcol") ? +$("upcol").value : res.valueCol, order: $("uporder") ? $("uporder").value : undefined, date1904: res.date1904, decimalComma: dc });
        r2.table = res.table; r2.date1904 = res.date1904; r2.decimalComma = dc; r2.decimalAsk = res.decimalAsk; r2.readWarns = res.readWarns;
        r2.notes = res.notes.filter(function (x) { return /sheet|workbook/i.test(x); }).concat(r2.notes);
        r2.warnings = (res.readWarns || []).concat(r2.warnings);
        applyUpload(r2, fname, true);
      } catch (er) { $("err").textContent = er.message; $("err").hidden = false; }
    }
    if ($("upcol")) $("upcol").addEventListener("change", rebuild);
    if ($("uporder")) $("uporder").addEventListener("change", rebuild);
    if ($("updec")) $("updec").addEventListener("change", rebuild);
    $("busy").hidden = true;
    run();
  }
  function cycleName(m, u) {
    var names = { 4: "quarters in a year", 5: "business days in a week", 7: "days in a week", 12: "months in a year", 24: "hours in a day", 52: "weeks in a year", 60: u === "second" ? "seconds in a minute" : "minutes in an hour" };
    return names[m] || "a " + m + "-" + u + " cycle";
  }

  // ---- wiring -------------------------------------------------------------
  function init() {
    fillSeries();
    $("series").addEventListener("change", function (e) { choose(e.target.value); });
    var ft; $("find").addEventListener("input", function () { clearTimeout(ft); ft = setTimeout(fillSeries, 120); });
    [["h", "h"], ["test", "test"], ["m", "m"]].forEach(function (p) { $(p[0]).addEventListener("change", function (e) {
      if (e.target.value === "custom") return;
      state[p[1]] = +e.target.value;
      if (p[0] === "test") state.testPref = state.test;
      if (p[0] === "m") current().m = state.m;
      run();
    }); });
    $("cmp").addEventListener("change", function (e) { state.compare = e.target.value; run(); });
    $("view").addEventListener("change", function (e) { state.view = e.target.value; run(); });
    $("dots").addEventListener("change", function (e) { state.dots = e.target.value; run(); });
    $("more").addEventListener("click", function () { state.more = !state.more; this.setAttribute("aria-pressed", String(state.more)); this.textContent = state.more ? "Fewer measures" : "More measures"; if (last) table(last.ranked); });
    $("file").addEventListener("change", function (e) {
      var f = e.target.files[0]; if (!f) return;
      e.target.value = "";
      var rd = new FileReader();
      $("busy").hidden = false; $("err").hidden = true;
      rd.onload = function () {
        window.FCUpload.read(rd.result, f.name).then(function (res) { applyUpload(res, f.name, false); })
          .catch(function (er) { $("busy").hidden = true; $("err").textContent = "Could not read “" + f.name + "”: " + er.message; $("err").hidden = false; });
      };
      rd.readAsArrayBuffer(f);
    });
    $("m").addEventListener("change", function (e) {
      if (e.target.value === "custom") { $("mcustom").hidden = false; $("mcustom").focus(); return; }
      $("mcustom").hidden = true;
    }, true);
    $("mcustom").addEventListener("change", function (e) {
      var v = Math.round(+e.target.value);
      if (!(v >= 1 && v <= 400)) { e.target.value = state.m; return; }
      state.m = v; current().m = v; run();
    });
    $("dl").addEventListener("click", downloadCSV);
    var t; window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(run, 150); });
    run();
  }
  document.addEventListener("DOMContentLoaded", init);
})();
