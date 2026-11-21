/* Upload reader: CSV / TSV / text exports and Excel .xlsx workbooks, read in the browser.
 * Finds the value column and the date column, reads many date formats, detects the time
 * unit (seconds to years, or plain period numbers) and suggests a seasonal period.
 * Exposes FCUpload.read(arrayBuffer, fileName, opts) -> Promise<result> and
 * FCUpload.build(table, opts) for re-running with a different column or date order.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- text decoding
  function decode(buf) {
    var b = new Uint8Array(buf), enc = "utf-8", start = 0;
    if (b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF) start = 3;
    else if (b[0] === 0xFF && b[1] === 0xFE) { enc = "utf-16le"; start = 2; }
    else if (b[0] === 0xFE && b[1] === 0xFF) { enc = "utf-16be"; start = 2; }
    else {
      var zeroOdd = 0, zeroEven = 0, n = Math.min(b.length, 2000);
      for (var i = 0; i < n; i++) if (b[i] === 0) { if (i % 2) zeroOdd++; else zeroEven++; }
      if (zeroOdd > n / 8) enc = "utf-16le"; else if (zeroEven > n / 8) enc = "utf-16be";
    }
    var body = b.subarray(start);
    if (enc === "utf-8") {
      try { return new TextDecoder("utf-8", { fatal: true }).decode(body); }
      catch (e) { return new TextDecoder("windows-1252").decode(body); } // older Excel "CSV" exports
    }
    return new TextDecoder(enc).decode(body);
  }

  // ---------------------------------------------------------------- CSV parsing
  function splitRows(text, delim) { // RFC 4180 style: quotes, doubled quotes, newlines inside quotes
    var rows = [], row = [], cell = "", q = false, i = 0, c;
    text = text.replace(/\r\n?/g, "\n");
    for (; i < text.length; i++) {
      c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
        else cell += c;
      } else if (c === '"' && cell.trim() === "") { q = true; cell = ""; }
      else if (c === delim) { row.push(cell); cell = ""; }
      else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
      else cell += c;
    }
    if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
    return rows.filter(function (r) { return r.some(function (x) { return String(x).trim() !== ""; }); });
  }
  function parseDelimited(text) {
    var best = null;
    [",", ";", "\t", "|"].forEach(function (d) {
      var rows = splitRows(text, d), counts = {};
      rows.slice(0, 200).forEach(function (r) { if (r.length > 1) counts[r.length] = (counts[r.length] || 0) + 1; });
      var top = 0; Object.keys(counts).forEach(function (k) { top = Math.max(top, counts[k]); });
      if (!best || top > best.score) best = { score: top, rows: rows, delim: d };
    });
    if (!best.score) best.rows = splitRows(text, "\u0000"); // one column of numbers
    return best;
  }

  // ---------------------------------------------------------------- numbers
  function toNumber(v, decimalComma) {
    if (typeof v === "number") return isFinite(v) ? v : null;
    if (v && typeof v === "object") return null; // a date cell
    var s = String(v).replace(/[\s  '’]/g, "").replace(/^[="]+|"+$/g, "");
    if (!s) return null;
    var neg = false;
    if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
    s = s.replace(/^[$€£¥₹]|[$€£¥₹]$/g, "").replace(/(USD|EUR|GBP)$/i, "");
    var pct = /%$/.test(s); if (pct) s = s.slice(0, -1);
    if (/^-?[$€£¥₹]/.test(s)) s = s.replace(/[$€£¥₹]/, "");
    if (decimalComma) s = s.replace(/\./g, "").replace(",", ".");
    else if (/^-?\d{1,3}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
    else if (/^-?\d+,\d{1,2}$/.test(s)) s = s.replace(",", ".");
    else s = s.replace(/,(?=\d{3}(\D|$))/g, "");
    if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) return null;
    var x = parseFloat(s); if (neg) x = -x;
    return isFinite(x) ? x : null;
  }

  // ---------------------------------------------------------------- dates
  var MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
    january: 1, february: 2, march: 3, april: 4, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12 };
  function y2(y) { return y < 100 ? (y < 70 ? 2000 + y : 1900 + y) : y; }
  function serialToParts(n, date1904) {
    var ms = Math.round((n + (date1904 ? 24107 : 0) - 25569) * 86400000), d = new Date(ms);
    return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes(), s: d.getUTCSeconds(), g: (n % 1) ? "time" : "day" };
  }
  function timeOf(s) { // "13:45", "1:45 PM", "13:45:10"
    var m = /(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?m\.?)?/i.exec(s);
    if (!m) return null;
    var h = +m[1]; if (m[4]) { var pm = /p/i.test(m[4]); if (h === 12) h = pm ? 12 : 0; else if (pm) h += 12; }
    return { h: h, mi: +m[2], s: m[3] ? +m[3] : 0 };
  }
  /* Parse one cell. Numeric day/month dates come back with an "amb" pair when either
   * reading is possible; the column-level pass decides (see resolveOrder). */
  function parseDate(v, date1904) {
    if (v && typeof v === "object" && "serial" in v) return serialToParts(v.serial, date1904);
    if (typeof v === "number") return null;
    var s = String(v).trim().replace(/^'+|^`+/, ""), m, t;
    if (!s) return null;
    t = timeOf(s);
    var core = s.replace(/[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\s*([ap]\.?m\.?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i, "").trim();
    if (t && /^\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\s*([ap]\.?m\.?)?$/i.test(core)) core = "";
    function out(y, mo, d, g) { return { y: y, mo: mo, d: d || 1, h: t ? t.h : 0, mi: t ? t.mi : 0, s: t ? t.s : 0, g: t ? "time" : g }; }
    if ((m = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(core))) return out(+m[1], +m[2], +m[3], "day");          // 2020-01-22
    if ((m = /^(\d{4})(\d{2})(\d{2})$/.exec(core)) && +m[2] <= 12 && +m[3] <= 31 && +m[1] > 1800) return out(+m[1], +m[2], +m[3], "day"); // 20200122
    if ((m = /^(\d{4})[-/.](\d{1,2})$/.exec(core)) && +m[2] <= 12) return out(+m[1], +m[2], 1, "month");          // 2020-01
    if ((m = /^(\d{4})\s*[-_ ]?\s*[Qq]([1-4])$/.exec(core)) || (m = /^[Qq]([1-4])\s*[-_/ ]?\s*'?(\d{2,4})$/.exec(core))) { // 2020Q1, Q1 2020
      var yq = m[0][0].toUpperCase() === "Q" ? y2(+m[2]) : +m[1], q = m[0][0].toUpperCase() === "Q" ? +m[1] : +m[2];
      return out(yq, q * 3 - 2, 1, "quarter");
    }
    if ((m = /^(\d{4})[-_ ]?W(\d{1,2})$/i.exec(core))) { // ISO week 2020-W05 -> Monday of that week
      var jan4 = Date.UTC(+m[1], 0, 4), dow = (new Date(jan4).getUTCDay() + 6) % 7, mon = new Date(jan4 - dow * 864e5 + (+m[2] - 1) * 7 * 864e5);
      return out(mon.getUTCFullYear(), mon.getUTCMonth() + 1, mon.getUTCDate(), "day");
    }
    if ((m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$/.exec(core))) {                                                  // 1/22/2020 or 22/1/2020
      var a = +m[1], b = +m[2], yy = y2(+m[3]);
      return { y: yy, a: a, b: b, amb: true, h: t ? t.h : 0, mi: t ? t.mi : 0, s: t ? t.s : 0, g: t ? "time" : "day" };
    }
    if ((m = /^(\d{1,2})[-/.](\d{4})$/.exec(core)) && +m[1] <= 12) return out(+m[2], +m[1], 1, "month");          // 01/2020
    // month names: 22-Jan, Jan-22, Jan 2020, January 22, 2020, 22 Jan 2020, 2020 Jan
    var toks = core.replace(/,/g, " ").split(/[\s\-/.]+/).filter(Boolean), mon2 = null, nums = [];
    toks.forEach(function (x) {
      var k = x.toLowerCase().replace(/\.$/, "");
      if (MONTHS[k] && mon2 === null) mon2 = { v: MONTHS[k], pos: nums.length };
      else if (/^\d{1,4}(st|nd|rd|th)?$/i.test(x)) nums.push(parseInt(x, 10));
      else if (!/^(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*$/i.test(k)) nums.push(NaN);
    });
    if (mon2 && nums.every(function (x) { return !isNaN(x); })) {
      if (nums.length === 0) return { y: null, mo: mon2.v, d: 1, g: "month", noYear: true, h: 0, mi: 0, s: 0 };
      if (nums.length === 1) {
        var x = nums[0];
        if (x >= 1000) return out(x, mon2.v, 1, "month");                                    // Jan 2020
        if (mon2.pos === 1 && x <= 31) return { y: null, mo: mon2.v, d: x, g: "day", noYear: true, h: 0, mi: 0, s: 0 }; // 22-Jan (Excel d-mmm)
        if (mon2.pos === 0 && x <= 99) return { y: null, mo: mon2.v, d: 1, x: x, monYY: true, g: "month", h: 0, mi: 0, s: 0 }; // Jan-22: Jan 2022 or Jan 22? decided per column
      }
      if (nums.length === 2) {
        var yr = nums.filter(function (x) { return x >= 1000; })[0], dd = nums.filter(function (x) { return x < 1000; })[0];
        if (yr && dd && dd <= 31) return out(yr, mon2.v, dd, "day");                           // 22 Jan 2020 / Jan 22, 2020
        if (!yr && mon2.pos === 1 && nums[0] <= 31) return out(y2(nums[1]), mon2.v, nums[0], "day"); // 22-Jan-20
      }
    }
    if ((m = /^(\d{4})$/.exec(core)) && +m[1] >= 1800 && +m[1] <= 2200) return out(+m[1], 1, 1, "year");
    if (t && !core) return { y: null, mo: 1, d: 1, h: t.h, mi: t.mi, s: t.s, g: "time", noYear: true, timeOnly: true };
    return null;
  }

  function toMs(p) { return Date.UTC(p.y, p.mo - 1, p.d, p.h || 0, p.mi || 0, p.s || 0); }
  function valid(p) { return p.mo >= 1 && p.mo <= 12 && p.d >= 1 && p.d <= 31; }

  // Decide month/day vs day/month for the whole column.
  function resolveOrder(parts, force) {
    var amb = parts.filter(function (p) { return p && p.amb; });
    if (!amb.length) return { order: null, ambiguous: false };
    var aMax = 0, bMax = 0;
    amb.forEach(function (p) { aMax = Math.max(aMax, p.a); bMax = Math.max(bMax, p.b); });
    var order, ambiguous = false, how;
    if (force) { order = force; how = "chosen by you"; }
    else if (aMax > 12 && bMax <= 12) { order = "DMY"; how = "a first number above 12"; }
    else if (bMax > 12 && aMax <= 12) { order = "MDY"; how = "a second number above 12"; }
    else {
      // Both readings are valid for every date: prefer the one that gives evenly spaced, increasing dates.
      var score = function (o) {
        var ms = amb.map(function (p) { return Date.UTC(p.y, (o === "MDY" ? p.a : p.b) - 1, o === "MDY" ? p.b : p.a); });
        var gaps = []; for (var i = 1; i < ms.length; i++) gaps.push(Math.abs(ms[i] - ms[i - 1]));
        gaps.sort(function (x, y) { return x - y; });
        var med = gaps[Math.floor(gaps.length / 2)] || 0, off = 0;
        gaps.forEach(function (g) { if (Math.abs(g - med) > 3 * 864e5) off++; });
        return off;
      };
      var sm = score("MDY"), sd = score("DMY");
      order = sd < sm ? "DMY" : "MDY"; ambiguous = true;
      how = sd === sm ? "no way to tell from the data; US month/day assumed" : "the reading that gives evenly spaced dates";
    }
    amb.forEach(function (p) { p.mo = order === "MDY" ? p.a : p.b; p.d = order === "MDY" ? p.b : p.a; });
    return { order: order, ambiguous: ambiguous || !!force, how: how };
  }

  // ---------------------------------------------------------------- time unit
  var UNITS = [ // name, typical gap in seconds, default seasonal period, other sensible periods
    { id: "second", one: "second", many: "seconds", sec: 1, m: 60 },
    { id: "minute", one: "minute", many: "minutes", sec: 60, m: 60 },
    { id: "hour", one: "hour", many: "hours", sec: 3600, m: 24 },
    { id: "day", one: "day", many: "days", sec: 86400, m: 7 },
    { id: "bday", one: "business day", many: "business days", sec: 86400, m: 5 },
    { id: "week", one: "week", many: "weeks", sec: 604800, m: 52 },
    { id: "month", one: "month", many: "months", sec: 2629746, m: 12 },
    { id: "quarter", one: "quarter", many: "quarters", sec: 7889238, m: 4 },
    { id: "year", one: "year", many: "years", sec: 31556952, m: 1 },
    { id: "period", one: "period", many: "periods", sec: 0, m: 1 }
  ];
  function unit(id) { return UNITS.filter(function (u) { return u.id === id; })[0]; }
  function detectUnit(ms) {
    var gaps = []; for (var i = 1; i < ms.length; i++) gaps.push((ms[i] - ms[i - 1]) / 1000);
    gaps.sort(function (a, b) { return a - b; });
    var g = gaps[Math.floor(gaps.length / 2)];
    if (!g) return "period";
    if (g < 30) return "second";
    if (g < 1800) return "minute";
    if (g < 43200) return "hour";
    if (g < 4 * 86400) { // daily: business days if weekends never appear
      var wk = 0; ms.forEach(function (x) { var d = new Date(x).getUTCDay(); if (d === 0 || d === 6) wk++; });
      return wk === 0 && ms.length > 10 && gaps.some(function (x) { return x >= 3 * 86400 - 1; }) ? "bday" : "day";
    }
    if (g < 20 * 86400) return "week";
    if (g < 60 * 86400) return "month";
    if (g < 200 * 86400) return "quarter";
    return "year";
  }

  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmt(ms, u, noYear) {
    var d = new Date(ms), y = d.getUTCFullYear(), mo = d.getUTCMonth(), dd = d.getUTCDate();
    var day = dd + " " + MON[mo] + (noYear ? "" : " " + y);
    if (u === "second" || u === "minute" || u === "hour") return (noYear && u !== "hour" ? "" : day + " ") + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + (u === "second" ? ":" + pad(d.getUTCSeconds()) : "");
    if (u === "day" || u === "bday" || u === "week") return day;
    if (u === "month") return MON[mo] + (noYear ? "" : " " + y);
    if (u === "quarter") return y + " Q" + (Math.floor(mo / 3) + 1);
    if (u === "year") return String(y);
    return String(ms);
  }
  function step(ms, u, k, gapSec) {
    var d = new Date(ms);
    if (u === "month" || u === "quarter" || u === "year") {
      var add = u === "month" ? k : u === "quarter" ? 3 * k : 12 * k;
      return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + add, Math.min(d.getUTCDate(), 28), d.getUTCHours(), d.getUTCMinutes());
    }
    if (u === "bday") { var x = ms, n = 0; while (n < k) { x += 864e5; var w = new Date(x).getUTCDay(); if (w !== 0 && w !== 6) n++; } return x; }
    return ms + k * gapSec * 1000;
  }

  // ---------------------------------------------------------------- table -> series
  /* table: array of rows, each an array of cells (string, number or {serial}).
   * opts: { valueCol, order: "MDY"|"DMY", date1904, sheet } */
  function build(table, opts) {
    opts = opts || {};
    var notes = [], warns = [], ncol = 0;
    table.forEach(function (r) { ncol = Math.max(ncol, r.length); });
    var dec = !!opts.decimalComma;
    // numeric share per column
    var stats = [];
    for (var c = 0; c < ncol; c++) {
      var num = 0, dat = 0, filled = 0;
      table.forEach(function (r) {
        var v = r[c]; if (v === undefined || v === null || String(typeof v === "object" ? "x" : v).trim() === "") return;
        filled++;
        var p = parseDate(v, opts.date1904);
        if (p) dat++;
        if (toNumber(v, dec) !== null) num++;
      });
      stats.push({ c: c, num: num, dat: dat, filled: filled });
    }
    var numericCols = stats.filter(function (s) { return s.num >= 5 && s.num >= 0.5 * s.filled; });
    if (!numericCols.length) throw new Error("No column of numbers found. The file needs one column of values (dates in another column are optional).");
    var vc = opts.valueCol !== undefined && numericCols.some(function (s) { return s.c === opts.valueCol; }) ? opts.valueCol
      : numericCols.slice().sort(function (a, b) {
        var da = a.dat >= 0.5 * a.filled ? 1 : 0, db = b.dat >= 0.5 * b.filled ? 1 : 0;
        return (da - db) || (b.num - a.num) || (b.c - a.c);
      })[0].c;
    // date column: most parseable dates; else a column of increasing integers (period numbers) left of the values
    var dc = null, bestDat = 0;
    stats.forEach(function (s) { if (s.c !== vc && s.dat > bestDat && s.dat >= 0.5 * s.filled) { bestDat = s.dat; dc = s.c; } });
    var periodCol = null;
    if (dc === null) stats.forEach(function (s) {
      if (s.c === vc || periodCol !== null || s.num < 5) return;
      var xs = table.map(function (r) { return toNumber(r[s.c], dec); }).filter(function (x) { return x !== null; });
      if (xs.every(function (x, i) { return Math.round(x) === x && (i === 0 || x === xs[i - 1] + 1); })) periodCol = s.c;
    });
    // header / name: last text cell above the first numeric value in the value column
    var first = 0; while (first < table.length && toNumber(table[first][vc], dec) === null) first++;
    var name = null;
    for (var h = first - 1; h >= 0 && name === null; h--) { var hv = table[h][vc]; if (hv !== undefined && String(hv).trim() && !/^[`'"\s]*$/.test(String(hv))) name = String(hv).trim(); }
    // collect rows
    var rows = [], skipped = 0;
    for (var i = first; i < table.length; i++) {
      var r = table[i], v = toNumber(r[vc], dec);
      if (v === null) { if (r.some(function (x) { return x !== undefined && String(typeof x === "object" ? "x" : x).trim() !== ""; })) skipped++; continue; }
      rows.push({ v: v, raw: dc !== null ? r[dc] : periodCol !== null ? r[periodCol] : null, p: dc !== null ? parseDate(r[dc], opts.date1904) : null });
    }
    if (skipped) warns.push(skipped + " row" + (skipped > 1 ? "s" : "") + " without a number in the value column " + (skipped > 1 ? "were" : "was") + " skipped.");
    var u = "period", ms = null, noYear = false, orderInfo = { order: null, ambiguous: false }, gapSec = 0;
    if (dc !== null) {
      var bad = rows.filter(function (x) { return !x.p; }).length;
      if (bad) { warns.push(bad + " row" + (bad > 1 ? "s" : "") + " had a date that could not be read and " + (bad > 1 ? "were" : "was") + " dropped."); rows = rows.filter(function (x) { return x.p; }); }
      orderInfo = resolveOrder(rows.map(function (x) { return x.p; }), opts.order);
      var my = rows.filter(function (x) { return x.p.monYY; });
      if (my.length) { // "Jan-22": Excel's mmm-yy (January 2022) unless neighbouring rows share a month, which means days
        var same = 0; for (var q = 1; q < my.length; q++) if (my[q].p.mo === my[q - 1].p.mo) same++;
        var asDay = same > my.length / 3;
        my.forEach(function (x) { if (asDay) { x.p.d = x.p.x; x.p.noYear = true; x.p.y = null; x.p.g = "day"; } else { x.p.y = y2(x.p.x); } });
        notes.push(asDay ? "Dates like “" + String(my[0].raw) + "” were read as month and day." : "Dates like “" + String(my[0].raw) + "” were read as month and two-digit year (Excel’s mmm-yy).");
      }
      noYear = rows.some(function (x) { return x.p.noYear; });
      if (noYear) { // e.g. "22-Jan" with no year: count years forward from 2001 when the month wraps
        // Pick a starting year that puts any 29 Feb on a leap year (the year itself is never shown).
        var leap = function (y) { return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0; };
        var assign = function (base) {
          var yr = base, prev = null, ok = true;
          rows.forEach(function (x) {
            var cur = x.p.mo * 100 + x.p.d;
            if (x.p.timeOnly) { x.p.y = base; x.p.mo = 1; x.p.d = 1; return; }
            if (prev !== null && cur < prev) yr++;
            x.p.y = yr; prev = cur;
            if (x.p.mo === 2 && x.p.d === 29 && !leap(yr)) ok = false;
          });
          return ok;
        };
        for (var base = 2001; base <= 2004; base++) if (assign(base)) break;
        notes.push("Dates have no year, so years are counted from the first row.");
      }
      rows = rows.filter(function (x) { return valid(x.p); });
      rows.forEach(function (x) { x.ms = toMs(x.p); });
      if (rows.length > 1 && rows[0].ms > rows[rows.length - 1].ms) { rows.reverse(); notes.push("Rows were newest-first, so they were put in date order."); }
      var unsorted = rows.some(function (x, k) { return k && x.ms < rows[k - 1].ms; });
      if (unsorted) { rows.sort(function (a, b) { return a.ms - b.ms; }); warns.push("Rows were out of date order and have been sorted."); }
      var dup = 0; rows = rows.filter(function (x, k) { if (k && x.ms === rows[k - 1].ms) { dup++; return false; } return true; });
      if (dup) warns.push(dup + " duplicate date" + (dup > 1 ? "s were" : " was") + " found; only the first row for each date was kept.");
      ms = rows.map(function (x) { return x.ms; });
      u = detectUnit(ms);
      var gaps = []; for (var j = 1; j < ms.length; j++) gaps.push((ms[j] - ms[j - 1]) / 1000);
      gaps.sort(function (a, b) { return a - b; });
      gapSec = gaps[Math.floor(gaps.length / 2)] || 86400;
      var missing = 0;
      for (var k2 = 1; k2 < ms.length; k2++) { var g = (ms[k2] - ms[k2 - 1]) / 1000; if (g > gapSec * 1.6 && !(u === "bday" && g <= 4 * 86400) && !(u === "month" || u === "quarter" || u === "year") || ((u === "month" && g > 45 * 86400) || (u === "quarter" && g > 120 * 86400) || (u === "year" && g > 400 * 86400))) missing++; }
      if (missing) warns.push(missing + " gap" + (missing > 1 ? "s" : "") + " in the dates (missing " + unit(u).many + "). Methods treat the series as evenly spaced, so results around the gaps are less reliable.");
    } else if (periodCol !== null) notes.push("No dates found; the period numbers in the file are used.");
    else notes.push("No dates found; rows are treated as periods 1, 2, 3, … in file order.");
    var U = unit(u);
    var labels = ms ? ms.map(function (x) { return fmt(x, u, noYear); }) : rows.map(function (x, k) { return "Period " + (x.raw !== null && x.raw !== undefined && String(x.raw).trim() ? String(x.raw).trim() : k + 1); });
    return {
      values: rows.map(function (x) { return x.v; }), dates: labels, ms: ms, unit: u, unitOne: U.one, unitMany: U.many, gapSec: gapSec, noYear: noYear,
      suggestedM: U.m, name: name, valueCol: vc, numericCols: numericCols.filter(function (s) { return s.c !== dc && s.c !== periodCol; }).map(function (s) { return { c: s.c, label: headerFor(table, s.c, first) }; }),
      dateCol: dc, order: orderInfo.order, orderAmbiguous: orderInfo.ambiguous, orderHow: orderInfo.how, notes: notes, warnings: warns,
      future: function (k) {
        var out = [];
        if (!ms) { for (var q = 1; q <= k; q++) out.push("Period " + (rows.length + q)); return out; }
        for (var q2 = 1; q2 <= k; q2++) out.push(fmt(step(ms[ms.length - 1], u, q2, gapSec), u, noYear));
        return out;
      }
    };
  }
  function headerFor(table, c, first) {
    for (var h = first - 1; h >= 0; h--) { var v = table[h][c]; if (v !== undefined && String(v).trim() && !/^[`'"\s]*$/.test(String(v))) return String(v).trim(); }
    var L = ""; var n = c + 1; while (n > 0) { var r = (n - 1) % 26; L = String.fromCharCode(65 + r) + L; n = Math.floor((n - 1) / 26); }
    return "Column " + L;
  }

  // ---------------------------------------------------------------- .xlsx (zip of XML)
  function u16(b, o) { return b[o] | (b[o + 1] << 8); }
  function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }
  function unzip(buf) {
    var b = new Uint8Array(buf), eocd = -1;
    for (var i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) if (u32(b, i) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error("This Excel file looks damaged (no zip directory).");
    var n = u16(b, eocd + 10), off = u32(b, eocd + 16), files = {};
    for (var k = 0; k < n; k++) {
      if (u32(b, off) !== 0x02014b50) break;
      var method = u16(b, off + 10), csize = u32(b, off + 20), nlen = u16(b, off + 28), xlen = u16(b, off + 30), clen = u16(b, off + 32), lho = u32(b, off + 42);
      var name = new TextDecoder().decode(b.subarray(off + 46, off + 46 + nlen));
      var dataStart = lho + 30 + u16(b, lho + 26) + u16(b, lho + 28);
      files[name] = { method: method, data: b.subarray(dataStart, dataStart + csize) };
      off += 46 + nlen + xlen + clen;
    }
    return files;
  }
  function inflate(entry) {
    if (entry.method === 0) return Promise.resolve(new TextDecoder().decode(entry.data));
    if (typeof DecompressionStream === "undefined") return Promise.reject(new Error("This browser cannot open Excel files. Save the sheet as CSV and upload that."));
    var ds = new DecompressionStream("deflate-raw");
    var stream = new Blob([entry.data]).stream().pipeThrough(ds);
    return new Response(stream).text();
  }
  var DATE_FMT_IDS = { 14: 1, 15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1, 21: 1, 22: 1, 27: 1, 30: 1, 36: 1, 45: 1, 46: 1, 47: 1, 50: 1, 57: 1 };
  function isDateCode(code) {
    var c = String(code).replace(/"[^"]*"/g, "").replace(/\[[^\]]*\]/g, "").replace(/\\./g, "");
    return /[dmyhs]/i.test(c) && !/^[#0.,%E+\-\s]*$/.test(c) && !/General/i.test(c);
  }
  function colIndex(ref) { var m = /^([A-Z]+)/.exec(ref), n = 0; for (var i = 0; i < m[1].length; i++) n = n * 26 + m[1].charCodeAt(i) - 64; return n - 1; }
  function xml(s) { return new DOMParser().parseFromString(s, "application/xml"); }
  function byTag(node, tag) { return Array.prototype.slice.call(node.getElementsByTagNameNS("*", tag)); }
  function readXlsx(buf) {
    var files = unzip(buf);
    function get(path) { var f = files[path] || files[path.replace(/^\//, "")]; return f ? inflate(f) : Promise.resolve(null); }
    return Promise.all([get("xl/workbook.xml"), get("xl/_rels/workbook.xml.rels"), get("xl/sharedStrings.xml"), get("xl/styles.xml")]).then(function (r) {
      if (!r[0]) throw new Error("This zip file is not an Excel workbook.");
      var wb = xml(r[0]), rels = r[1] ? xml(r[1]) : null, sst = [], dateStyle = [];
      var pr = byTag(wb, "workbookPr")[0], date1904 = pr && /^(1|true)$/.test(pr.getAttribute("date1904") || "");
      if (r[2]) byTag(xml(r[2]), "si").forEach(function (si) { sst.push(byTag(si, "t").map(function (t) { return t.textContent; }).join("")); });
      if (r[3]) {
        var st = xml(r[3]), custom = {};
        byTag(st, "numFmt").forEach(function (f) { custom[f.getAttribute("numFmtId")] = f.getAttribute("formatCode"); });
        var xfs = byTag(st, "cellXfs")[0];
        if (xfs) byTag(xfs, "xf").forEach(function (xf) { var id = +xf.getAttribute("numFmtId"); dateStyle.push(!!(DATE_FMT_IDS[id] || (custom[id] && isDateCode(custom[id])))); });
      }
      var relMap = {};
      if (rels) byTag(rels, "Relationship").forEach(function (x) { relMap[x.getAttribute("Id")] = x.getAttribute("Target"); });
      var sheets = byTag(wb, "sheet").map(function (s) {
        var rid = s.getAttribute("r:id") || s.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id");
        var target = relMap[rid] || "";
        var path = target.charAt(0) === "/" ? target.slice(1) : "xl/" + target.replace(/^\.\//, "");
        return { name: s.getAttribute("name"), path: path };
      });
      return Promise.all(sheets.map(function (s) { return get(s.path); })).then(function (texts) {
        return sheets.map(function (s, i) {
          var table = [];
          if (texts[i]) byTag(xml(texts[i]), "row").forEach(function (row) {
            var rn = +row.getAttribute("r") - 1, arr = [];
            byTag(row, "c").forEach(function (c, ci) {
              var ref = c.getAttribute("r"), col = ref ? colIndex(ref) : ci, t = c.getAttribute("t"), v = byTag(c, "v")[0], val = null;
              if (t === "s") val = v ? sst[+v.textContent] : "";
              else if (t === "inlineStr") val = byTag(c, "t").map(function (x) { return x.textContent; }).join("");
              else if (t === "str" || t === "e") val = v ? v.textContent : "";
              else if (t === "b") val = v ? v.textContent : "";
              else if (t === "d") val = v ? v.textContent : "";
              else if (v) { var num = parseFloat(v.textContent); val = dateStyle[+(c.getAttribute("s") || 0)] ? { serial: num } : num; }
              arr[col] = val;
            });
            table[isNaN(rn) ? table.length : rn] = arr;
          });
          return { name: s.name, table: table.filter(Boolean).map(function (r) { for (var j = 0; j < r.length; j++) if (r[j] === undefined) r[j] = ""; return r; }), date1904: date1904 };
        });
      });
    });
  }

  // ---------------------------------------------------------------- entry point
  function read(buf, fileName, opts) {
    opts = opts || {};
    var b = new Uint8Array(buf);
    if (b[0] === 0x50 && b[1] === 0x4B && b[2] === 0x03 && b[3] === 0x04) {
      return readXlsx(buf).then(function (sheets) {
        var errors = [];
        for (var i = 0; i < sheets.length; i++) {
          try {
            var res = build(sheets[i].table, { date1904: sheets[i].date1904, valueCol: opts.valueCol, order: opts.order });
            if (res.values.length < 5) throw new Error("too few numbers");
            if (sheets.length > 1) res.notes.unshift("Used sheet “" + sheets[i].name + "”.");
            if (/\.csv$/i.test(fileName)) res.notes.unshift("This file is an Excel workbook saved with a .csv name; it was read as a workbook.");
            res.table = sheets[i].table; res.date1904 = sheets[i].date1904; res.source = "Excel workbook";
            return res;
          } catch (e) { errors.push(sheets[i].name); }
        }
        throw new Error("No sheet in this workbook has a column of numbers (checked " + errors.join(", ") + ").");
      });
    }
    if (b[0] === 0xD0 && b[1] === 0xCF && b[2] === 0x11 && b[3] === 0xE0)
      return Promise.reject(new Error("This is an older Excel .xls file. In Excel, use File › Save As › Excel Workbook (.xlsx) or CSV, then upload that."));
    return new Promise(function (resolve) {
      var text = decode(buf), p = parseDelimited(text);
      var res = build(p.rows, { valueCol: opts.valueCol, order: opts.order, decimalComma: p.delim === ";" && /\d,\d/.test(text) && !/\d\.\d/.test(text) });
      res.table = p.rows; res.decimalComma = p.delim === ";" && /\d,\d/.test(text) && !/\d\.\d/.test(text); res.source = "text file";
      resolve(res);
    });
  }

  var api = { read: read, build: build, parseDate: parseDate, toNumber: toNumber, decode: decode, parseDelimited: parseDelimited, UNITS: UNITS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.FCUpload = api;
})(this);
