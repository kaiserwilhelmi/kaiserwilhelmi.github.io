/* Engine edge cases (Node, no browser): flat histories, non-numbers, filled values that must
 * not be scored, NaN-safe ranking, and MASE unchanged when the series is rescaled.
 * Run: node test/test_engine.js   (exit code 1 on any failure) */
const E = require("../engine.js");
let fails = 0;
function check(name, ok, detail) { console.log((ok ? "ok   " : "FAIL ") + name + (ok || !detail ? "" : "  (" + detail + ")")); if (!ok) fails++; }
const fin = r => r.results.every(x => isFinite(x.metrics.MASE));

// 1. constant series: the seasonal-naive scale is 0, so MASE falls back to the average level
const flat = Array(60).fill(100);
let r = E.score(E.prepare(flat, 12), { h: 6, test: 24 });
check("constant series: finite MASE for every method", fin(r), r.scaleBase);
check("constant series: scale falls back to the level", r.scaleBase === "level" && r.scale === 100, r.scaleBase + " " + r.scale);

// 2. flat for 40 months, then moving: the scale falls back, ranking still works
const step = flat.map((v, i) => i < 40 ? 100 : 100 + (i - 39) * (i % 2 ? 3 : -2));
r = E.score(E.prepare(step, 12), { h: 6, test: 24 });
check("flat history then movement: finite MASE", fin(r), r.scaleBase);
check("flat history then movement: ranking has no NaN", E.rank(r.results).every(x => isFinite(x.metrics.MASE)));

// 3. a single unchanged month inside a seasonal series keeps the seasonal-naive scale
const seas = Array.from({ length: 72 }, (_, i) => 100 + 10 * Math.sin(2 * Math.PI * i / 12) + i * 0.5);
r = E.score(E.prepare(seas, 12), { h: 6, test: 24 });
check("ordinary seasonal series: seasonal-naive scale", r.scaleBase === "snaive", r.scaleBase);

// 4. non-numbers are rejected with a clear message
let msg = ""; try { E.prepare(seas.slice(0, 50).concat([NaN], seas.slice(51)), 12); } catch (e) { msg = e.message; }
check("NaN in the series is rejected", /Value 51 .*not a number/.test(msg), msg);

// 5. filled values are used for fitting but never scored
const skip = [60, 66];
const P = E.prepare(seas, 12, null, skip);
r = E.score(P, { h: 6, test: 24 });
const hit = r.results.some(x => x.records.some(q => skip.indexOf(q.idx) >= 0));
check("filled values are never scoring targets", !hit);
const r1 = E.score(P, { h: 1, test: 24 });
check("an origin whose only target was filled has no loss", r1.results.every(x => x.loss.length === 24 - skip.length), r1.results[0].loss.length);
check("stability check runs with filled values", E.stability(P, 6).length >= 2);

// 6. ranking puts non-finite MASE last instead of sorting arbitrarily
const fake = [{ id: "a", metrics: { MASE: NaN, RMSE: 1 } }, { id: "b", metrics: { MASE: 0.5, RMSE: 1 } }, { id: "c", metrics: { MASE: 0.4, RMSE: 1 } }];
check("rank: NaN goes last", E.rank(fake).map(x => x.id).join("") === "cba", E.rank(fake).map(x => x.id).join(""));

// 7. MASE does not depend on the units of the series (x1000)
const a = E.score(E.prepare(seas, 12), { h: 6, test: 24 }), b = E.score(E.prepare(seas.map(v => v * 1000), 12), { h: 6, test: 24 });
const ids = ["naive", "snaive", "drift", "ma3", "tslm"];
const same = ids.every(id => Math.abs(a.results.find(x => x.id === id).metrics.MASE - b.results.find(x => x.id === id).metrics.MASE) < 1e-9);
check("MASE unchanged when values are multiplied by 1,000", same);

console.log(fails ? fails + " check(s) failed" : "all engine checks passed"); process.exit(fails ? 1 : 0);
