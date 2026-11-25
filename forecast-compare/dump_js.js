// Runs engine.js over every series and setting combo; writes js_results.json for verify.py.
const fs = require("fs");
const E = require("./engine.js");
const files = ["SAMPLE_demand", "FRGSHPUSM649NCIS", "PCU322211322211", "PCOPPUSDM", "DJFUELUSGULF"];
const out = [];
const nul = v => (isFinite(v) ? v : null);
function record(label, path, m, test, h, P) {
  const r = E.score(P, { h, test }), nv = r.results.find(q => q.id === "naive"), ranked = E.rank(r.results);
  const others = ranked.filter(x => x.id !== "naive"), adj = E.holm(others.map(x => E.dmTest(x.loss, nv.loss).p));
  const rest = ranked.slice(1), adjB = E.holm(rest.map(x => E.dmTest(x.loss, ranked[0].loss).p));
  const proc = x => x && { metrics: x.metrics, maeByH: x.maeByH, loss: x.loss, future: x.future, dmNaive: nul(E.dmTest(x.loss, nv.loss).p) };
  out.push({ label, file: path, m, test, h, scale: r.scale, lo: P.lo, ranked: ranked.map(x => x.id), members: r.members,
    holmNaive: Object.fromEntries(others.map((x, i) => [x.id, nul(adj[i])])), holmBest: Object.fromEntries(rest.map((x, i) => [x.id, nul(adjB[i])])),
    pool: proc(r.pool), pick: proc(r.pick), picks: r.picks, hindsight: proc(r.hindsight),
    results: r.results.map(x => ({ id: x.id, metrics: x.metrics, maeByH: x.maeByH, loss: x.loss, dm: x.id === "naive" ? null : nul(E.dmTest(x.loss, nv.loss).p), future: x.future, params: x.params })) });
}
for (const f of files) {
  const path = "data/" + f + ".csv";
  const y = fs.readFileSync(path, "utf8").trim().split(/\r?\n/).slice(1).map(l => +l.split(",")[1]);
  for (const m of [12, 1]) {
    const P = E.prepare(y, m);
    for (const test of [12, 24, 36]) for (const h of [1, 3, 6, 12]) if (test <= P.W && test >= 2 * h) record(`${f} m=${m} test=${test} h=${h}`, path, m, test, h, P);
  }
}
// uploaded-style series with other time units (daily m=7, business-day m=5, hourly m=24, weekly m=52, quarterly m=4)
for (const [f, m] of [["test/daily_cases.csv", 7], ["test/business_days.csv", 5], ["test/hourly_load.csv", 24], ["test/weekly_orders.csv", 52], ["test/quarterly_spend.csv", 4]]) {
  const y = fs.readFileSync(f, "utf8").trim().split(/\r?\n/).slice(1).map(l => +l.split(",")[1]);
  const P = E.prepare(y, m);
  for (const h of [1, 6]) if (24 <= P.W) record(`${f} m=${m} test=24 h=${h}`, f, m, 24, h, P);
}
fs.writeFileSync("js_results.json", JSON.stringify(out));
console.log("cases", out.length);
