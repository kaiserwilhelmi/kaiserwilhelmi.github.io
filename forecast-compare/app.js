/* UI for the forecast comparison page. Depends on FCEngine (engine.js) and SERIES (inlined data). */
(function () {
  "use strict";
  var E = window.FCEngine, SERIES = window.SERIES, MW = window.MW_CATALOG || { groups: [], items: [] }, MK = window.FCMarket;
  var $ = function (id) { return document.getElementById(id); };
  var state = { key: SERIES[0].key, upload: null, h: 6, test: 24, m: 12, compare: "naive", sort: "rank", dir: 1 };
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
    var every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - pad.l) / 70))));
    for (var i = 0; i < n; i += every) s += '<text x="' + X(i) + '" y="' + (H - 8) + '" text-anchor="' + (i === 0 ? "start" : i === n - 1 ? "end" : "middle") + '" class="ax">' + esc(cfg.xfmt(cfg.labels[i])) + "</text>";
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
    return items.map(function (it) { return '<span class="lg"><i style="background:' + it.color + (it.dash ? ";background:repeating-linear-gradient(90deg," + it.color + " 0 5px,transparent 5px 8px)" : "") + '"></i>' + esc(it.name) + "</span>"; }).join("");
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
    return Object.keys(p).map(function (k) { return sym[k] + " " + (k === "slope" ? fmtV(p[k]) : p[k].toFixed(2)); }).join(", ");
  }

  // Fitting every method at every origin is the slow part, so it runs once per
  // series + seasonality and every horizon/window choice is scored from it. It fits twice
  // the backtest window: the older half is what the page uses to test its own choice.
  var cache = {};
  function run() {
    var s = current(), key = s.key + "|" + (s.uid || s.name) + "|" + state.m, err = $("err"), P = cache[key];
    unitLabels(s);
    err.hidden = true;
    var need = 2 * Math.max(state.test, state.testPref || 0);
    if (P && !moreNeeded(P, need)) return render(s, P);
    $("busy").innerHTML = P ? "<b>Fitting older origins to test the choice…</b>" : "<b>Fitting every method at each backtest origin…</b>"; $("busy").hidden = false;
    setTimeout(function () {
      try { if (P) E.ensure(P, need); else cache[key] = P = E.prepare(s.values, state.m, null, s.skip || [], need); }
      catch (e) { $("busy").hidden = true; err.textContent = e.message; err.hidden = false; return; }
      $("busy").hidden = true;
      render(s, P);
    }, 30);
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
    var ref = s.values[s.values.length - 1];
    last = { s: s, res: res, ranked: ranked, byId: byId, dec: dec, prim: prim, P: P };

    // tag + KPIs
    $("tag").innerHTML = s.sample ? '<span class="badge">SAMPLE DATA · synthetic, for demonstration</span>' : "";
    var ev = dec.kind === "naive" ? dec.row : prim.r, hz = state.h + " " + (state.h > 1 ? many(s) : one(s)) + " ahead";
    var how = dec.honest ? "re-picked at each origin, " + hz : "in the window used to choose (optimistic)";
    $("kpis").innerHTML =
      kpi("Recommended forecast", dec.kind === "naive" ? "Naive" : prim.name,
        dec.kind === "pool" ? "average of " + poolNames.join(", ") : dec.kind === "naive" ? "the latest value; " + (dec.tried === "pick" ? "the re-picked best method" : "the top-3 pool") + " did not beat it" : "best single method, re-picked at each origin") +
      kpi(dec.kind === "naive" ? (dec.tried === "pick" ? "Best method vs naive" : "Top-3 pool vs naive") : "Error vs naive", relText(relPct(ev.metrics.MAE, nv.metrics.MAE)), "MAE, " + how) +
      (sn ? kpi(dec.kind === "naive" ? "Naive vs seasonal naive" : "Error vs seasonal naive", relText(relPct((dec.kind === "naive" ? nv : ev).metrics.MAE, sn.metrics.MAE)), "same forecasts and targets")
        : kpi("Best in hindsight", best.name, "MASE " + fmt(best.metrics.MASE, 3) + " used to choose" + (res.pick ? ", " + fmt(res.pick.metrics.MASE, 3) + " re-picked" : ""))) +
      kpi("Forecasts scored", ev.metrics.n, res.origins + " origins × " + hz);

    $("rec").innerHTML = recommend(s, res, ranked, byId, dec, prim, poolNames, ref);
    honestTable(s, res, byId, best);

    // compare picker
    if (state.compare === prim.id || !byId[state.compare]) state.compare = prim.id === "naive" ? (best.id === "naive" ? ranked[1].id : best.id) : "naive";
    $("cmp").innerHTML = meths.filter(function (d) { return d.id !== prim.id; }).map(function (d) {
      return '<option value="' + d.id + '"' + (d.id === state.compare ? " selected" : "") + ">" + esc(displayName(d.id, d.name, s)) + "</option>";
    }).join("");
    var cmp = byId[state.compare];

    // main chart
    var n = s.values.length, fut = futureDates(s.dates, 12, s), labels = s.dates.concat(fut);
    var actual = s.values.map(function (v, i) { return [i, v]; });
    function bt(r) { return r.records.filter(function (q) { return q.k === 1; }).map(function (q) { return [q.idx, q.f]; }); }
    function fu(f) { return [[n - 1, s.values[n - 1]]].concat(f.map(function (v, i) { return [n + i, v]; })); }
    var C1 = "var(--s1)", C2 = "var(--s2)", CA = "var(--text)";
    var series = [
      { name: "Actual", color: CA, pts: actual },
      { name: prim.name + " (backtest, 1-step)", color: C1, pts: bt(prim.r), dots: true },
      { name: prim.name + " (forecast)", color: C1, pts: fu(prim.future) },
      { name: cmp.name + " (backtest, 1-step)", color: C2, pts: bt(cmp), dots: true, dash: true },
      { name: cmp.name + " (forecast)", color: C2, pts: fu(cmp.future), dash: true }
    ];
    $("lg1").innerHTML = legend([{ name: "Actual", color: CA }, { name: prim.name + " (recommended)", color: C1 }, { name: cmp.name, color: C2, dash: true }]);
    lineChart($("ch1"), { labels: labels, series: series, xfmt: label, ref: ref, band: [res.first - 0.5 < 0 ? 0 : res.first - 0.5, n - 1], bandLabel: "Backtest window",
      aria: "Actual values with backtest and 12-" + one(s) + " forecasts for " + prim.name + " and " + cmp.name, height: 320 });

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
    $("ch1t").textContent = "Actuals, backtest and 12-" + one(s) + " forecast";
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

  function recommend(s, res, ranked, byId, dec, prim, poolNames, ref) {
    var best = ranked[0], nv = byId.naive, u1 = one(s), unit = s.short ? " " + esc(s.short) : "";
    var hz = state.h + " " + (state.h > 1 ? many(s) : one(s)) + " ahead", out;
    var honestP = res.pool ? E.holm([E.dmTest(res.pool.loss, nv.loss).p, E.dmTest(res.pick.loss, nv.loss).p]) : null;
    var why = "Averaging a few strong methods is safer than betting on one, because the top-ranked method is partly there by luck (Kourentzes, Barrow &amp; Petropoulos, 2019).";
    if (dec.kind === "pool") {
      out = "<h2>Recommendation: average the top 3 methods</h2><ul>";
      out += "<li>Average the forecasts of " + nameList(poolNames) + ", the three methods with the lowest error over the last " + state.test + " " + many(s) + ". " + why + "</li>";
    } else if (dec.kind === "pick") {
      out = "<h2>Recommendation: use " + esc(best.name) + "</h2><ul>";
      out += "<li>Picking the single best method at each past " + u1 + " beat the top-3 pool on this series by a margin that is unlikely to be luck (" + pf(dec.pickVsPool.p) + "). Today that method is " + esc(best.name) + ".</li>";
    } else {
      out = "<h2>Recommendation: plan on the latest value (naive)</h2><ul>";
    }
    var r = dec.row, g = relPct(r.metrics.MAE, nv.metrics.MAE), who = dec.kind === "naive" ? (dec.tried === "pick" ? "the re-picked single best method" : "the top-3 pool") : dec.kind === "pick" ? "this approach" : "the pool";
    if (!dec.honest) {
      out += "<li>This series is too short to test the choice itself with a " + state.test + "-" + u1 + " window: that needs " + res.needN + " " + many(s) + " and it has " + s.values.length + ". " +
        "The numbers here come from the window used to choose, so they flatter the result. In that window " + who + " missed by " + fmtV(r.metrics.MAE, ref) + unit + " on average at " + hz + ", " +
        fmt(Math.abs(g), 1) + "% " + (g <= 0 ? "less" : "more") + " than naive." + (dec.kind === "naive" ? " Even so it did not beat naive, so the latest value is the planning number." : "") + " A shorter backtest window may allow the full test.</li>";
    } else {
      var pAdj = honestP[dec.tried === "pick" ? 1 : 0];
      if (dec.kind === "naive") {
        out += "<li>Tested the way you would use it (" + (dec.tried === "pick" ? "the best method" : "the top 3") + " picked again at each past " + u1 + " from only the errors known then), " + who + " did not beat naive: its error was " + fmt(Math.abs(g), 1) + "% " + (g <= 0 ? "lower" : "higher") +
          " at " + hz + ". For this series the latest value is as good a planning number as any model here, so effort is better spent on contract terms or hedging than on a model.</li>";
      } else {
        out += "<li>Tested the way you would use it (" + (dec.kind === "pool" ? "the top 3 picked" : "the best method picked") + " again at each past " + u1 + " from only the errors known then), " + who + " missed by " + fmtV(r.metrics.MAE, ref) + unit +
          " on average at " + hz + ", " + fmt(Math.abs(g), 1) + "% less than naive. " +
          (!isFinite(pAdj) ? "Whether that edge is real cannot be tested here: the errors do not vary enough." : pAdj < 0.05 ? "That edge is <b>statistically significant</b> (" + pf(pAdj) + ")." :
            "The backtest is too short to tell whether that edge is real (" + pf(pAdj) + "), so naive remains a reasonable fallback.") + "</li>";
        if (g > -5) out += "<li>An edge under 5% is small. Treat the series as close to a random walk: plan around the latest value and put effort into hedging or contract terms.</li>";
      }
      out += "<li>The best single method in the table, " + esc(best.name) + ", scored MASE " + fmt(best.metrics.MASE, 3) + " over this window, but that is the score it was picked on, so it flatters it. " +
        "Picking the single best method at each past " + u1 + " scored " + fmt(res.pick.metrics.MASE, 3) + " on what came next, against " + fmt(res.pool.metrics.MASE, 3) + " for the top-3 pool." +
        (dec.kind === "pool" && res.pick.metrics.MAE < res.pool.metrics.MAE ? " That difference is too small for the backtest to separate, so the pool stays the safer default." : "") + "</li>";
    }
    out += tiedText(ranked, res, s);
    var winners = {};
    ["RMSE", "MAPE", "sMAPE"].forEach(function (k) {
      var w = ranked.filter(function (x) { return x.metrics[k] !== null; }).sort(function (a, b) { return a.metrics[k] - b.metrics[k]; })[0];
      if (w && w.id !== best.id) (winners[w.name] = winners[w.name] || []).push(k);
    });
    var dis = Object.keys(winners);
    if (dis.length) out += "<li>Other error measures would rank a different method first: " + dis.map(function (n) { return esc(n) + " on " + winners[n].join(" and "); }).join("; ") +
      ". The table ranks by MASE, which orders methods the same way as MAE. Use RMSE instead when one large miss costs more than several small ones (Kolassa, 2020).</li>";
    var bias = r.metrics.ME, rel = Math.abs(bias) / r.metrics.MAE;
    if (dec.kind !== "naive" && rel > 0.5) out += "<li>Watch the bias: it tends to " + (bias > 0 ? "under" : "over") + "-forecast (mean error " + fmtV(bias, ref) + "). " + (bias > 0 ? "Budget and safety stock set from it will run short." : "Budget set from it will be padded.") + "</li>";
    out += "<li>Next " + u1 + ": <b>" + fmtV(prim.future[0], ref) + "</b>" + unit + ", 12-" + u1 + " path in the chart below.</li></ul>";
    return out;
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
    var worse = others.filter(function (r) { return vb[r.id] < 0.05; }).map(function (r) { return r.name; });
    var tied = others.length - worse.length, lim = "With " + res.origins + " overlapping origins the significance test only separates large, steady differences";
    if (!worse.length) return "<li>" + lim + ", and none of the other " + others.length + " methods was shown to be worse than " + esc(best.name) +
      ". So the ranking is a guide only, which is one reason the page pools the top three.</li>";
    if (!tied) return "<li>Every other method scored significantly worse than " + esc(best.name) + " in this window.</li>";
    return "<li>" + (worse.length > 5 ? worse.length + " methods were" : nameList(worse) + (worse.length > 1 ? " were" : " was")) + " shown to be worse than " + esc(best.name) +
      ". " + lim + ", so the other " + tied + " are statistically tied with it and their order in the table is not reliable.</li>";
  }

  // Testing the choice itself: each approach is re-picked at every past origin from the errors
  // known then, and scored on what happened next. The hindsight row is shown for contrast.
  function honestTable(s, res, byId, best) {
    var nv = byId.naive, sn = byId.snaive, el = $("honest");
    if (!res.pool) {
      el.innerHTML = '<p class="hint" style="margin:0">Testing the choice needs at least ' + res.needN + " " + many(s) + " of history with a " + state.test + "-" + one(s) +
        " backtest window; this series has " + s.values.length + ". Pick a shorter window, or read the ranking below as optimistic.</p>";
      return;
    }
    var p = E.holm([E.dmTest(res.pool.loss, nv.loss).p, E.dmTest(res.pick.loss, nv.loss).p]);
    var rows = [
      { name: "Top-3 pool", note: "Average of the three best methods, re-picked at each origin", r: res.pool, p: p[0], cls: "win" },
      { name: "Best single method", note: "The top method, re-picked at each origin", r: res.pick, p: p[1] },
      { name: "Naive", note: "Benchmark: the latest value", r: nv, p: null }
    ];
    if (sn) rows.push({ name: "Seasonal naive", note: "Benchmark: the value one cycle earlier", r: sn, p: null });
    rows.push({ name: esc(best.name) + ", best in hindsight", note: "Scored on the window it was picked on, so this number is optimistic", r: best, p: null, cls: "dim" });
    var ref = s.values[s.values.length - 1];
    var h = '<table><thead><tr><th class="l">Approach</th><th title="Mean absolute scaled error">MASE</th><th title="Mean absolute error, in the series\' units">MAE</th><th>RMSE</th><th title="Mean error, actual minus forecast">Bias (ME)</th>' +
      '<th title="MAE relative to naive on the same forecasts (Davydenko &amp; Fildes, 2013)">vs naive</th>' + (sn ? '<th title="MAE relative to seasonal naive on the same forecasts">vs seasonal naive</th>' : "") +
      '<th title="Diebold-Mariano test against naive, fixed-b variance, Holm-adjusted over the two re-picked approaches">p vs naive</th></tr></thead><tbody>';
    rows.forEach(function (o) {
      var m = o.r.metrics, isNv = o.r === nv;
      h += "<tr" + (o.cls ? ' class="' + o.cls + '"' : "") + '><td class="l"><b>' + o.name + '</b><div class="ref">' + esc(o.note) + "</div></td><td>" + fmt(m.MASE, 3) + "</td><td>" + fmt(m.MAE, digits(ref)) + "</td><td>" + fmt(m.RMSE, digits(ref)) +
        "</td><td>" + fmt(m.ME, digits(ref)) + "</td><td>" + (isNv ? "–" : relText(relPct(m.MAE, nv.metrics.MAE))) + "</td>" + (sn ? "<td>" + (o.r === sn ? "–" : relText(relPct(m.MAE, sn.metrics.MAE))) + "</td>" : "") +
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
    var bestOf = {}, pv = pvCells(ranked), vb = last.vb || vsBest(ranked), pool = last.res.members;
    COLS.forEach(function (c) {
      var v = ranked.map(function (r) { var m = r.metrics[c.k]; return m === null ? Infinity : c.k === "ME" ? Math.abs(m) : m; });
      bestOf[c.k] = Math.min.apply(null, v);
    });
    var ref = last.s.values[last.s.values.length - 1];
    var h = '<table><thead><tr><th data-k="rank" class="l">#</th><th class="l">Method</th>' +
      COLS.map(function (c) { return '<th data-k="' + c.k + '" title="' + esc(c.tip) + '">' + c.t + (state.sort === c.k ? (state.dir > 0 ? " ▲" : " ▼") : "") + "</th>"; }).join("") +
      '<th title="Diebold-Mariano test against naive (fixed-b variance), Holm-adjusted across the table. Below 0.05 = significantly different.">p vs naive</th>' +
      '<th title="Diebold-Mariano test against the #1 method, Holm-adjusted. Tied = not shown to be worse; with few origins the test only separates large, steady differences.">vs #1</th><th class="l">Fitted parameters</th></tr></thead><tbody>';
    rows.forEach(function (o) {
      var r = o.r, m = r.metrics, p1 = vb[r.id];
      var v1 = o.rank === 1 ? "–" : !(p1 < 0.05) ? "tied" : "worse, " + (p1 < 0.001 ? "p<0.001" : "p " + fmt(p1, 3));
      h += '<tr' + (o.rank === 1 ? ' class="win"' : "") + '><td class="l">' + o.rank + '</td><td class="l"><b>' + esc(r.name) + "</b>" + (pool.indexOf(r.id) >= 0 ? ' <span class="pill">in pool</span>' : "") + '<div class="ref">' + esc(r.note) + " " + esc(r.ref) + "</div></td>" +
        COLS.map(function (c) {
          var v = m[c.k], isBest = v !== null && (c.k === "ME" ? Math.abs(v) : v) === bestOf[c.k];
          var d = c.k === "MASE" ? 3 : (c.k === "MAPE" || c.k === "sMAPE") ? 2 : c.k === "MSE" ? digits(v) : digits(ref);
          return "<td" + (isBest ? ' class="best" title="Best in column"' : "") + ">" + (isBest ? "★ " : "") + fmt(v, d) + "</td>";
        }).join("") + "<td>" + pv[r.id] + "</td><td>" + v1 + '</td><td class="l pm">' + esc(paramText(r.params)) + "</td></tr>";
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

  function downloadCSV() {
    if (!last) return;
    var lines = ["method,origin_date,steps_ahead,target_date,actual,forecast,error"];
    var rows = last.res.results.slice();
    if (last.res.pool) rows.push({ name: "Top-3 pool (re-picked at each origin)", records: last.res.pool.records }, { name: "Best single method (re-picked at each origin)", records: last.res.pick.records });
    rows.forEach(function (r) {
      r.records.forEach(function (q) {
        lines.push([JSON.stringify(r.name), last.s.dates[q.origin - 1], q.k, last.s.dates[q.idx], q.y, q.f, q.e].join(","));
      });
    });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    a.download = "backtest-" + String(last.s.key || "series").replace(/[^A-Za-z0-9_-]+/g, "-") + ".csv"; document.body.appendChild(a); a.click(); a.remove();
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
