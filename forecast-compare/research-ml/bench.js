// Benchmark: all methods on many real series; rolling origin (last 36 origins, h=6).
const fs = require("fs"), E = require("./engine.js"), ML = require("./ml.js");
const H = 6, W = 36, withMLP = process.argv.includes("--mlp");
function load(p) { return fs.readFileSync(p, "utf8").trim().split(/\r?\n/).slice(1).map(l => +l.split(",")[1]).filter(v => isFinite(v)); }
const sets = [];
for (const f of fs.readdirSync("../market-watch/data/raw")) sets.push({ name: f.replace(".csv", ""), y: load("/home/user/market-watch/data/raw/" + f), m: 12 });
sets.push({ name: "SAMPLE", y: load("data/SAMPLE_demand.csv"), m: 12 });
for (const [f, m] of [["test/daily_cases.csv", 7], ["test/business_days.csv", 5], ["test/hourly_load.csv", 24], ["test/weekly_orders.csv", 52], ["test/quarterly_spend.csv", 4]]) sets.push({ name: f, y: load(f), m });
const NEW = { theta: ML.theta, ridge: ML.ridge, gbm: ML.gbm }; if (withMLP) NEW.mlp = ML.mlp;
const out = [];
let t0 = Date.now();
for (const s of sets) {
  const y = s.y, n = y.length, m = s.m;
  if (n - W < E.minTrain(m)) continue;
  const meths = E.activeMethods(m).filter(d => !d.parts), fc = {};
  for (const d of meths) { fc[d.id] = {}; for (let T = n - W; T < n; T++) fc[d.id][T] = d.fn(y.slice(0, T), H, m).f; }
  for (const k in NEW) { fc[k] = {}; for (let T = n - W; T < n; T++) fc[k][T] = NEW[k](y.slice(0, T), H, m).f; }
  const avg = ids => { const o = {}; for (let T = n - W; T < n; T++) { o[T] = []; for (let k = 0; k < H; k++) o[T].push(ids.reduce((a, i) => a + fc[i][T][k], 0) / ids.length); } return o; };
  if (m > 1) fc.combS = avg(["hw", "sarima"]); else fc.combN = avg(["ses", "holt", "damped"]);
  if (m > 1) fc.combS3 = avg(["hw", "sarima", "theta"]); else fc.combN3 = avg(["ses", "holt", "damped", "theta"]);
  fc.combML = avg(["ridge", "gbm"].concat(withMLP ? ["mlp"] : []));
  out.push({ name: s.name, m, n, y, fc });
  process.stderr.write(".");
}
fs.writeFileSync(withMLP ? "bench_mlp.json" : "bench.json", JSON.stringify(out));
console.error("\nseries", out.length, "secs", (Date.now() - t0) / 1000);
