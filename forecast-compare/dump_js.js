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
        results: r.results.map(x => ({ id: x.id, metrics: x.metrics, maeByH: x.maeByH, future: x.future, params: x.params })) });
    }
  }
}
fs.writeFileSync("js_results.json", JSON.stringify(out));
console.log("cases", out.length);
