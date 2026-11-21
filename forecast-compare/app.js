/* UI for the forecast comparison page. Depends on FCEngine (engine.js) and SERIES (inlined data). */
(function () {
  "use strict";
  var E = window.FCEngine, SERIES = window.SERIES;
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
  function futureDates(dates, k) {
    var a = parseYM(dates[dates.length - 2]), b = parseYM(dates[dates.length - 1]), out = [];
    if (!a || !b) { for (var i = 1; i <= k; i++) out.push("t+" + i); return out; }
    var step = (b.y - a.y) * 12 + (b.m - a.m) || 1, cur = b.y * 12 + b.m - 1;
    for (var j = 1; j <= k; j++) { var c = cur + j * step; out.push(Math.floor(c / 12) + "-" + String(c % 12 + 1).padStart(2, "0") + "-01"); }
    return out;
  }

  // ---- data ---------------------------------------------------------------
  function current() {
    if (state.key === "upload" && state.upload) return state.upload;
    return SERIES.filter(function (s) { return s.key === state.key; })[0];
  }
  function parseCSV(text, name) {
    var lines = text.replace(/\r/g, "").split("\n").filter(function (l) { return l.trim(); });
    var dates = [], vals = [];
    lines.forEach(function (l) {
      var cells = l.split(/[,;\t]/).map(function (c) { return c.trim().replace(/^"|"$/g, ""); });
      if (cells.length < 2) return;
      var v = parseFloat(cells[cells.length - 1].replace(/[$\s]/g, ""));
      if (!isFinite(v)) return; // header or blank value
      dates.push(cells[0]); vals.push(v);
    });
    return { key: "upload", name: name, unit: "", source: "Uploaded by you (stays in your browser)", sample: false, dates: dates, values: vals };
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
    { k: "MASE", t: "MASE", tip: "Mean absolute scaled error. Below 1 = better than a seasonal-naive forecast on the training data. Ranks the table." },
    { k: "MAE", t: "MAE", tip: "Mean absolute error, in the series' own units." },
    { k: "RMSE", t: "RMSE", tip: "Root mean squared error. Punishes big misses more than MAE." },
    { k: "MSE", t: "MSE", tip: "Mean squared error (RMSE squared)." },
    { k: "MAPE", t: "MAPE %", tip: "Mean absolute percentage error. Undefined if any actual is zero; favours under-forecasts." },
    { k: "sMAPE", t: "sMAPE %", tip: "Symmetric MAPE: error divided by the average of actual and forecast." },
    { k: "ME", t: "Bias (ME)", tip: "Mean error, actual minus forecast. Positive = the method under-forecasts on average." }
  ];

  function paramText(p) {
    if (!p) return "";
    var sym = { alpha: "α", beta: "β", gamma: "γ", phi: "φ", slope: "slope", theta: "θ", Theta: "Θ" };
    return Object.keys(p).map(function (k) { return sym[k] + " " + (k === "slope" ? fmtV(p[k]) : p[k].toFixed(2)); }).join(", ");
  }

  // Fitting every method at every origin is the slow part, so it runs once per
  // series + seasonality and every horizon/window choice is scored from it.
  var cache = {};
  function run() {
    var s = current(), key = s.key + "|" + (s.name) + "|" + state.m, err = $("err");
    err.hidden = true;
    if (cache[key]) return render(s, cache[key]);
    $("busy").hidden = false;
    setTimeout(function () {
      try { cache[key] = E.prepare(s.values, state.m); }
      catch (e) { $("busy").hidden = true; err.textContent = e.message; err.hidden = false; return; }
      $("busy").hidden = true;
      render(s, cache[key]);
    }, 30);
  }

  function render(s, P) {
    var err = $("err");
    Array.prototype.forEach.call($("test").options, function (o) { o.disabled = +o.value > P.W; });
    if (state.test > P.W) { state.test = P.W; $("test").value = String(P.W); }
    var meths = P.meths;
    if (!meths.some(function (d) { return d.id === state.compare; })) state.compare = "naive";
    var res;
    try { res = E.score(P, { h: state.h, test: state.test }); }
    catch (e) { err.textContent = e.message; err.hidden = false; return; }
    var ranked = E.rank(res.results);
    last = { s: s, res: res, ranked: ranked, stab: E.stability(P, state.h) };
    var best = ranked[0], nv = res.results.filter(function (r) { return r.id === "naive"; })[0];
    var ref = s.values[s.values.length - 1];

    // tag + KPIs
    $("tag").innerHTML = s.sample ? '<span class="badge">SAMPLE DATA · synthetic, for demonstration</span>' : "";
    var gain = 100 * (1 - best.metrics.MAE / nv.metrics.MAE);
    $("kpis").innerHTML =
      kpi("Best method", best.name, "lowest MASE of " + ranked.length) +
      kpi("Best MASE", fmt(best.metrics.MASE, 3), (best.metrics.MASE < 1 ? "beats" : "worse than") + " in-sample " + (state.m > 1 ? "seasonal naive" : "naive") + " (1-step)") +
      kpi("MAE vs naive", best.id === "naive" ? "0%" : (gain >= 0 ? "−" : "+") + fmt(Math.abs(gain), 1) + "%", best.id === "naive" ? "naive is the winner" : "error " + (gain >= 0 ? "lower" : "higher") + " than naive") +
      kpi("Forecasts scored", best.metrics.n, state.test + " origins × up to " + state.h + " step" + (state.h > 1 ? "s" : ""));

    // recommendation
    $("rec").innerHTML = recommend(s, ranked, nv, ref);

    // compare picker
    $("cmp").innerHTML = meths.filter(function (d) { return d.id !== best.id; }).map(function (d) {
      return '<option value="' + d.id + '"' + (d.id === state.compare ? " selected" : "") + ">" + esc(d.name) + "</option>";
    }).join("");
    if (state.compare === best.id) state.compare = $("cmp").value;
    var cmp = res.results.filter(function (r) { return r.id === state.compare; })[0];

    // main chart
    var n = s.values.length, fut = futureDates(s.dates, 12), labels = s.dates.concat(fut);
    var actual = s.values.map(function (v, i) { return [i, v]; });
    function bt(r) { return r.records.filter(function (q) { return q.k === 1; }).map(function (q) { return [q.idx, q.f]; }); }
    function fu(r) { return [[n - 1, s.values[n - 1]]].concat(r.future.map(function (v, i) { return [n + i, v]; })); }
    var C1 = "var(--s1)", C2 = "var(--s2)", CA = "var(--text)";
    var series = [
      { name: "Actual", color: CA, pts: actual },
      { name: best.name + " (backtest, 1-step)", color: C1, pts: bt(best), dots: true },
      { name: best.name + " (forecast)", color: C1, pts: fu(best) },
      { name: cmp.name + " (backtest, 1-step)", color: C2, pts: bt(cmp), dots: true, dash: true },
      { name: cmp.name + " (forecast)", color: C2, pts: fu(cmp), dash: true }
    ];
    $("lg1").innerHTML = legend([{ name: "Actual", color: CA }, { name: best.name + " (best)", color: C1 }, { name: cmp.name, color: C2, dash: true }]);
    lineChart($("ch1"), { labels: labels, series: series, xfmt: label, ref: ref, band: [res.first - 0.5 < 0 ? 0 : res.first - 0.5, n - 1], bandLabel: "Backtest window",
      aria: "Actual values with backtest and 12-period forecasts for " + best.name + " and " + cmp.name, height: 320 });

    // horizon chart
    if (state.h > 1) {
      $("hz").hidden = false;
      var hl = []; for (var k = 1; k <= state.h; k++) hl.push(k);
      var hs = [{ name: best.name, color: C1, pts: best.maeByH.map(function (v, i) { return [i, v]; }), dots: true },
        { name: cmp.name, color: C2, pts: cmp.maeByH.map(function (v, i) { return [i, v]; }), dots: true, dash: true }];
      $("lg2").innerHTML = legend([{ name: best.name, color: C1 }, { name: cmp.name, color: C2, dash: true }]);
      lineChart($("ch2"), { labels: hl, series: hs, xfmt: function (k) { return k + " ahead"; }, ref: ref, aria: "MAE by forecast horizon", height: 220, zero: true });
    } else $("hz").hidden = true;

    table(ranked);
    $("meta").innerHTML = esc(s.name) + (s.unit ? " · " + esc(s.unit) : "") + " · " + n + " observations, " + label(s.dates[0]) + " to " + label(s.dates[n - 1]) + " · Source: " + s.source;
  }

  function kpi(t, v, sub) { return '<div class="kpi"><div class="kt">' + esc(t) + '</div><div class="kv">' + esc(v) + '</div><div class="ks">' + esc(sub) + "</div></div>"; }

  function recommend(s, ranked, nv, ref) {
    var best = ranked[0], second = ranked[1];
    var out = "<h2>Recommendation: use " + esc(best.name) + "</h2><ul>";
    if (best.id === "naive") out += "<li>No method beat the naive forecast. For this series, last month's value is the best planning number; extra modelling adds complexity without accuracy.</li>";
    else {
      var gain = 100 * (1 - best.metrics.MASE / nv.metrics.MASE);
      out += "<li>Over the " + state.test + "-period backtest it was off by " + fmtV(best.metrics.MAE, ref) + (s.short ? " " + esc(s.short) : "") + " on average (MAE), " +
        fmt(Math.abs(gain), 1) + "% " + (gain >= 0 ? "better" : "worse") + " than the naive benchmark.</li>";
      if (gain < 5) out += "<li>That edge over naive is small (under 5%). Treat the series as close to a random walk: plan on the latest value and spend effort on hedging or contract terms rather than on a model.</li>";
    }
    var edge = 100 * (second.metrics.MASE / best.metrics.MASE - 1);
    if (edge < 2) out += "<li>" + esc(second.name) + " is within " + (edge < 0.1 ? "0.1" : fmt(edge, 1)) + "% on MASE, effectively a tie. Prefer the simpler of the two.</li>";
    var winners = {};
    ["MAE", "RMSE", "MAPE", "sMAPE"].forEach(function (k) {
      var w = ranked.filter(function (r) { return r.metrics[k] !== null; }).sort(function (a, b) { return a.metrics[k] - b.metrics[k]; })[0];
      if (w && w.id !== best.id) (winners[w.name] = winners[w.name] || []).push(k);
    });
    var dis = Object.keys(winners);
    if (dis.length) out += "<li>Metrics disagree: " + dis.map(function (n) { return esc(n) + " wins on " + winners[n].join(" and "); }).join("; ") + ". MASE is used for the ranking because it is scale-free and stays defined near zero (Hyndman &amp; Koehler, 2006).</li>";
    else out += "<li>Every error metric agrees on the winner.</li>";
    var bias = best.metrics.ME, rel = Math.abs(bias) / best.metrics.MAE;
    if (rel > 0.5) out += "<li>Watch the bias: it tends to " + (bias > 0 ? "under" : "over") + "-forecast (mean error " + fmtV(bias, ref) + "). " + (bias > 0 ? "Budget and safety stock set from it will run short." : "Budget set from it will be padded.") + "</li>";
    out += stabilityText(last.stab, best);
    var nxt = best.future[0];
    out += "<li>Next-period forecast: <b>" + fmtV(nxt, ref) + "</b>" + (s.short ? " " + esc(s.short) : "") + ", 12-period path in the chart below.</li></ul>";
    return out;
  }

  function stabilityText(rows, best) {
    if (rows.length < 2) return "";
    var ws = rows.map(function (r) { return r.test; }).join(", ");
    if (rows.every(function (r) { return r.winner === best.id; }))
      return "<li><b>Stable:</b> " + esc(best.name) + " also wins with " + ws + "-period backtest windows.</li>";
    var list = rows.map(function (r) { return r.test + " periods: " + esc(r.name); }).join("; ");
    if (rows.every(function (r) { return r.top3.indexOf(best.id) >= 0; }))
      return "<li><b>Mostly stable:</b> the winner changes with the backtest window (" + list + "), but " + esc(best.name) + " stays in the top 3 each time.</li>";
    return "<li><b>Not stable:</b> the winner changes with the backtest window (" + list + "). Treat the ranking as a shortlist, and lean toward the simpler or combined method.</li>";
  }

  function table(ranked) {
    var rows = ranked.map(function (r, i) { return { r: r, rank: i + 1 }; });
    if (state.sort !== "rank") rows.sort(function (a, b) {
      var x = a.r.metrics[state.sort], y = b.r.metrics[state.sort];
      if (state.sort === "ME") { x = Math.abs(x); y = Math.abs(y); }
      if (x === null) return 1; if (y === null) return -1;
      return state.dir * (x - y);
    });
    var bestOf = {};
    COLS.forEach(function (c) {
      var v = ranked.map(function (r) { var m = r.metrics[c.k]; return m === null ? Infinity : c.k === "ME" ? Math.abs(m) : m; });
      bestOf[c.k] = Math.min.apply(null, v);
    });
    var ref = last.s.values[last.s.values.length - 1];
    var h = '<table><thead><tr><th data-k="rank" class="l">#</th><th class="l">Method</th>' +
      COLS.map(function (c) { return '<th data-k="' + c.k + '" title="' + esc(c.tip) + '">' + c.t + (state.sort === c.k ? (state.dir > 0 ? " ▲" : " ▼") : "") + "</th>"; }).join("") +
      '<th class="l">Fitted parameters</th></tr></thead><tbody>';
    rows.forEach(function (o) {
      var r = o.r, m = r.metrics;
      h += '<tr' + (o.rank === 1 ? ' class="win"' : "") + '><td class="l">' + o.rank + '</td><td class="l"><b>' + esc(r.name) + '</b><div class="ref">' + esc(r.note) + " " + esc(r.ref) + "</div></td>" +
        COLS.map(function (c) {
          var v = m[c.k], isBest = v !== null && (c.k === "ME" ? Math.abs(v) : v) === bestOf[c.k];
          var d = c.k === "MASE" ? 3 : (c.k === "MAPE" || c.k === "sMAPE") ? 2 : c.k === "MSE" ? digits(v) : digits(ref);
          return "<td" + (isBest ? ' class="best" title="Best in column"' : "") + ">" + (isBest ? "★ " : "") + fmt(v, d) + "</td>";
        }).join("") + '<td class="l pm">' + esc(paramText(r.params)) + "</td></tr>";
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
    last.res.results.forEach(function (r) {
      r.records.forEach(function (q) {
        lines.push([JSON.stringify(r.name), last.s.dates[q.origin - 1], q.k, last.s.dates[q.idx], q.y, q.f, q.e].join(","));
      });
    });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    a.download = "backtest-" + (last.s.key || "series") + ".csv"; document.body.appendChild(a); a.click(); a.remove();
  }

  // ---- wiring -------------------------------------------------------------
  function init() {
    $("series").innerHTML = SERIES.map(function (s) { return '<option value="' + s.key + '">' + esc(s.name) + "</option>"; }).join("") +
      '<option value="upload" disabled>Uploaded CSV</option>';
    $("series").addEventListener("change", function (e) { state.key = e.target.value; run(); });
    [["h", "h"], ["test", "test"], ["m", "m"]].forEach(function (p) { $(p[0]).addEventListener("change", function (e) { state[p[1]] = +e.target.value; run(); }); });
    $("cmp").addEventListener("change", function (e) { state.compare = e.target.value; run(); });
    $("file").addEventListener("change", function (e) {
      var f = e.target.files[0]; if (!f) return;
      var rd = new FileReader();
      rd.onload = function () {
        var p = parseCSV(rd.result, f.name.replace(/\.[^.]+$/, ""));
        if (p.values.length < 10) { $("err").textContent = "Could not find a numeric value column in that file. Use two columns: date, value."; $("err").hidden = false; return; }
        state.upload = p; state.key = "upload";
        var o = $("series").querySelector('option[value="upload"]'); o.disabled = false; o.textContent = "Uploaded: " + p.name; $("series").value = "upload";
        run();
      };
      rd.readAsText(f);
    });
    $("dl").addEventListener("click", downloadCSV);
    var t; window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(run, 150); });
    run();
  }
  document.addEventListener("DOMContentLoaded", init);
})();
