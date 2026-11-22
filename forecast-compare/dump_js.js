// Runs engine.js over every series and setting combo; writes js_results.json for verify.py.
const fs = require("fs");
const E = require("./engine.js");
const files = ["SAMPLE_demand", "FRGSHPUSM649NCIS", "PCU322211322211", "PCOPPUSDM", "DJFUELUSGULF"];
const out = [];
for (const f of files) {
  const path = "data/" + f + ".csv";
  const y = fs.readFileSync(path, "utf8").trim().split(/\r?\n/).slice(1).map(l => +l.split(",")[1]);
  for (const m of [12, 1]) {
    const P = E.prepare(y, m);
    for (const test of [12, 24, 36]) for (const h of [1, 3, 6, 12]) {
      const r = E.score(P, { h, test });
      out.push({ label: `${f} m=${m} test=${test} h=${h}`, file: path, m, test, h, scale: r.scale,
        stability: E.stability(P, h).map(s => s.winner),
        results: r.results.map(x => ({ id: x.id, metrics: x.metrics, maeByH: x.maeByH, loss: x.loss, dm: x.id === 'naive' ? null : E.dmTest(x.loss, r.results.find(q => q.id === 'naive').loss, h).p, future: x.future, params: x.params })) });
    }
  }
}
// uploaded-style series with other time units (daily m=7, business-day m=5, hourly m=24, weekly m=52, quarterly m=4)
for (const [f, m] of [["test/daily_cases.csv", 7], ["test/business_days.csv", 5], ["test/hourly_load.csv", 24], ["test/weekly_orders.csv", 52], ["test/quarterly_spend.csv", 4]]) {
  const y = fs.readFileSync(f, "utf8").trim().split(/\r?\n/).slice(1).map(l => +l.split(",")[1]);
  const P = E.prepare(y, m);
  for (const h of [1, 6]) { const r = E.score(P, { h, test: 24 });
    out.push({ label: `${f} m=${m} test=24 h=${h}`, file: f, m, test: 24, h, scale: r.scale, stability: E.stability(P, h).map(s => s.winner),
      results: r.results.map(x => ({ id: x.id, metrics: x.metrics, maeByH: x.maeByH, loss: x.loss, dm: x.id === 'naive' ? null : E.dmTest(x.loss, r.results.find(q => q.id === 'naive').loss, h).p, future: x.future, params: x.params })) }); }
}
fs.writeFileSync("js_results.json", JSON.stringify(out));
console.log("cases", out.length);
