// Cleans every Market Watch series with mw.js (as the page does) and runs the engine on it.
// Output: JSON for test/verify_mw.py.  Usage: node test/dump_mw.js <market-watch repo> > mw_js.json
const fs = require("fs"), path = require("path");
const MK = require("../mw.js"), E = require("../engine.js"), U = require("../upload.js");
const mw = process.argv[2], out = { long: {}, spot: {}, runs: [] };
const ids = fs.readdirSync(path.join(mw, "data/long")).filter(f => f.endsWith(".csv")).map(f => f.slice(0, -4)).filter(i => i !== "CPIAUCSL");
for (const id of ids) {
  const p = MK.parseCSV(fs.readFileSync(path.join(mw, "data/long", id + ".csv"), "utf8")), c = MK.clean(p.dates, p.values);
  out.long[id] = c;
  const t = Date.now(), P = E.prepare(c.values, 12), r = E.score(P, { h: 6, test: 24 }), best = E.rank(r.results)[0];
  out.runs.push({ id, n: c.values.length, ms: Date.now() - t, best: best.id, mase: best.metrics.MASE, ok: r.results.every(x => isFinite(x.metrics.MASE)) });
}
const spot = JSON.parse(fs.readFileSync(path.join(mw, "data/agency/spot.json"), "utf8"));
for (const k of Object.keys(spot)) {
  const rows = spot[k], c = MK.clean(rows.map(r => String(r[0])), rows.map(r => (r[1] === null ? null : +r[1])));
  const res = U.build([["Date", k]].concat(c.dates.map((d, i) => [d, String(c.values[i])])), {});
  let m = res.suggestedM; if (m > 1 && res.values.length < E.minTrain(m) + 12) m = 1;
  out.spot[k] = { dates: c.dates, values: c.values, filled: c.filled, built: res.values, unit: res.unit, m };
  const t = Date.now(), P = E.prepare(res.values, m), r = E.score(P, { h: 6, test: Math.min(24, P.W) }), best = E.rank(r.results)[0];
  out.runs.push({ id: "spot:" + k, n: res.values.length, ms: Date.now() - t, best: best.id, mase: best.metrics.MASE, ok: r.results.every(x => isFinite(x.metrics.MASE)), unit: res.unit, m });
}
process.stdout.write(JSON.stringify(out));
