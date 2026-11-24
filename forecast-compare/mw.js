/* Loads Industry Market Watch series for the forecast page.
 * Monthly history (data/long/<id>.csv) and recent spot prices (data/agency/spot.json)
 * are read from the Market Watch site, which refreshes them every day.
 * Gaps inside a series (e.g. a month the publisher skipped) are filled by
 * straight-line interpolation, the same rule Market Watch uses; leading and
 * trailing blanks are dropped. Runs in the browser and in Node (tests). */
(function (root) {
  "use strict";
  var REL = "../market-watch/", ABS = "https://dawsonwilhelmi.com/market-watch/";

  function getText(path) {
    var local = typeof location !== "undefined" && /^https?:$/.test(location.protocol);
    var urls = local ? [REL + path, ABS + path] : [ABS + path];
    function attempt(i, lastErr) {
      if (i >= urls.length) return Promise.reject(lastErr);
      // give up after 15 s so a stalled request cannot leave "Loading…" on screen forever
      var ac = typeof AbortController !== "undefined" ? new AbortController() : null;
      var timer = ac ? setTimeout(function () { ac.abort(); }, 15000) : null;
      return fetch(urls[i], ac ? { signal: ac.signal } : undefined).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      }).then(function (t) { clearTimeout(timer); return t; }, function (e) {
        clearTimeout(timer);
        return attempt(i + 1, e && e.name === "AbortError" ? new Error("no answer after 15 seconds") : e);
      });
    }
    return attempt(0);
  }

  function num(x) {
    if (x === null || x === undefined) return null;
    var s = String(x).trim();
    if (s === "" || s === ".") return null;
    var v = +s;
    return isFinite(v) ? v : null;
  }

  // "date,value" CSV -> {dates, values} with null for blanks
  function parseCSV(text) {
    var lines = text.replace(/\r/g, "").split("\n").filter(function (l) { return l.trim() !== ""; });
    var dates = [], values = [];
    for (var i = 1; i < lines.length; i++) {
      var p = lines[i].split(",");
      dates.push(p[0].trim()); values.push(num(p[1]));
    }
    return { dates: dates, values: values };
  }

  // drop leading/trailing blanks, fill inside gaps linearly; returns filled dates
  function clean(dates, values) {
    var a = 0, b = values.length - 1;
    while (a <= b && values[a] === null) a++;
    while (b >= a && values[b] === null) b--;
    var d = dates.slice(a, b + 1), v = values.slice(a, b + 1), filled = [];
    for (var i = 0; i < v.length; i++) {
      if (v[i] !== null) continue;
      var j = i; while (v[j] === null) j++;
      var lo = i - 1, x0 = v[lo], x1 = v[j];
      for (var k = i; k < j; k++) { v[k] = x0 + (x1 - x0) * (k - lo) / (j - lo); filled.push(d[k]); }
      i = j;
    }
    return { dates: d, values: v, filled: filled, dropped: a + (values.length - 1 - b) };
  }

  function monthly(id) {
    return getText("data/long/" + encodeURIComponent(id) + ".csv").then(function (t) {
      var p = parseCSV(t), c = clean(p.dates, p.values);
      if (c.values.length < 10) throw new Error("only " + c.values.length + " values");
      return c;
    });
  }

  var spotCache = null;
  function spot(key) {
    if (!spotCache) spotCache = getText("data/agency/spot.json").then(JSON.parse).catch(function (e) { spotCache = null; throw e; });
    return spotCache.then(function (all) {
      var rows = all[key];
      if (!rows || !rows.length) throw new Error("no data for " + key);
      var c = clean(rows.map(function (r) { return String(r[0]); }), rows.map(function (r) { return num(r[1]); }));
      if (c.values.length < 10) throw new Error("only " + c.values.length + " values");
      return c;
    });
  }

  var api = { parseCSV: parseCSV, clean: clean, monthly: monthly, spot: spot, getText: getText, ABS: ABS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.FCMarket = api;
})(this);
