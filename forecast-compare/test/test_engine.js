/* Engine checks (Node, no browser): flat histories, non-numbers, filled values that must not be
 * scored, NaN-safe ranking, MASE unchanged when the series is rescaled, complete-origin scoring,
 * no look-ahead in the re-picked pool, the size of the Diebold-Mariano test, Holm, lazy fitting.
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
const seas = Array.from({ length: 100 }, (_, i) => 100 + 10 * Math.sin(2 * Math.PI * i / 12) + i * 0.5);
r = E.score(E.prepare(seas, 12), { h: 6, test: 24 });
check("ordinary seasonal series: seasonal-naive scale", r.scaleBase === "snaive", r.scaleBase);

// 4. non-numbers are rejected with a clear message
let msg = ""; try { E.prepare(seas.slice(0, 50).concat([NaN], seas.slice(51, 72)), 12); } catch (e) { msg = e.message; }
check("NaN in the series is rejected", /Value 51 .*not a number/.test(msg), msg);

// 5. filled values are used for fitting but never scored
const skip = [80, 86];
const P = E.prepare(seas, 12, null, skip);
r = E.score(P, { h: 6, test: 24 });
const hit = r.results.some(x => x.records.some(q => skip.indexOf(q.idx) >= 0));
check("filled values are never scoring targets", !hit);
const r1 = E.score(P, { h: 1, test: 24 });
check("an origin whose only target was filled has no loss", r1.results.every(x => x.loss.length === 24 - skip.length), r1.results[0].loss.length);
check("re-picked pool runs with filled values", r.pool && r.pool.records.every(q => skip.indexOf(q.idx) < 0));

// 6. ranking puts non-finite MASE last instead of sorting arbitrarily
const fake = [{ id: "a", metrics: { MASE: NaN, RMSE: 1 } }, { id: "b", metrics: { MASE: 0.5, RMSE: 1 } }, { id: "c", metrics: { MASE: 0.4, RMSE: 1 } }];
check("rank: NaN goes last", E.rank(fake).map(x => x.id).join("") === "cba", E.rank(fake).map(x => x.id).join(""));

// 7. MASE does not depend on the units of the series (x1000)
const a = E.score(E.prepare(seas, 12), { h: 6, test: 24 }), b = E.score(E.prepare(seas.map(v => v * 1000), 12), { h: 6, test: 24 });
const ids = ["naive", "snaive", "drift", "ma3", "tslm"];
const same = ids.every(id => Math.abs(a.results.find(x => x.id === id).metrics.MASE - b.results.find(x => x.id === id).metrics.MASE) < 1e-9);
check("MASE unchanged when values are multiplied by 1,000", same);


// 8. complete origins only: every origin has all h steps, and there are test - h + 1 of them
const S = E.prepare(seas, 12);
for (const [h, test] of [[6, 24], [12, 24], [1, 12], [6, 12]]) {
  const q = E.score(S, { h, test }), per = {};
  q.results[0].records.forEach(x => { per[x.origin] = (per[x.origin] || 0) + 1; });
  const counts = Object.values(per);
  check(`complete origins h=${h} window=${test}: ${test - h + 1} origins of ${h} steps`, counts.length === test - h + 1 && counts.every(c => c === h) && q.origins === test - h + 1, counts.length + " origins");
}
msg = ""; try { E.score(S, { h: 12, test: 12 }); } catch (e) { msg = e.message; }
check("a window shorter than twice the horizon is refused", /at least 24/.test(msg), msg);

// 9. no look-ahead: the pool picked at origin T uses only values before T
const y0 = seas.slice(), q0 = E.score(S, { h: 6, test: 24 }), T0 = q0.first + 5;
const S2 = Object.assign({}, S, { y: y0.map((v, i) => i >= T0 ? v + 500 * Math.cos(i) : v) });
const q2 = E.score(S2, { h: 6, test: 24 });
let same9 = true; for (let T = q0.first; T <= T0; T++) if (q0.picks[T].join() !== q2.picks[T].join()) same9 = false;
check("pool picks up to origin T ignore every value from T on", same9);
const T1 = q0.first + 3, mem = q0.picks[T1], rec = q0.pool.records.filter(x => x.origin === T1);
check("pool forecast = average of the 3 methods picked at that origin", rec.every(x => Math.abs(x.f - mem.reduce((s, id) => s + S.fc[id][T1][x.k - 1], 0) / 3) < 1e-9 * Math.abs(x.f)), mem.join());
const rk = E.rank(q0.results).slice(0, 3).map(x => x.id);
check("future pool = the table's top 3", q0.members.join() === rk.join() && q0.pool.future.every((v, k) => Math.abs(v - rk.reduce((s, id) => s + S.fut[id].f[k], 0) / 3) < 1e-9 * Math.abs(v)));
const pk = q0.pick.records.filter(x => x.origin === T1);
check("single pick forecast = the method ranked first at that origin", pk.every(x => x.f === S.fc[mem[0]][T1][x.k - 1]));

// 10. Diebold-Mariano (EWC, fixed-b): about 5% false alarms with 19 overlapping 6-step losses
let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
let rej = 0; const reps = 4000;
for (let i = 0; i < reps; i++) {
  const e = Array.from({ length: 24 }, gauss), f = Array.from({ length: 24 }, gauss), l1 = [], l2 = [];
  for (let t = 0; t < 19; t++) { let a = 0, b = 0; for (let k = 0; k < 6; k++) { a += Math.abs(e[t + k]); b += Math.abs(f[t + k]); } l1.push(a / 6); l2.push(b / 6); }
  if (E.dmTest(l1, l2).p < 0.05) rej++;
}
check("DM false-alarm rate near 5% (19 origins, h = 6)", rej / reps > 0.03 && rej / reps < 0.075, (100 * rej / reps).toFixed(1) + "%");
check("DM: identical losses give p = 1", E.dmTest([1, 2, 3], [1, 2, 3]).p === 1);
check("DM: a constant non-zero difference cannot be tested", isNaN(E.dmTest([2, 3, 4, 5], [1, 2, 3, 4]).p));

// 11. Holm adjustment
const hp = E.holm([0.01, 0.04, 0.03, NaN]);
check("Holm: [0.01, 0.04, 0.03, NaN] -> [0.03, 0.06, 0.06, NaN]", Math.abs(hp[0] - 0.03) < 1e-12 && Math.abs(hp[1] - 0.06) < 1e-12 && Math.abs(hp[2] - 0.06) < 1e-12 && isNaN(hp[3]), hp.join());

// 12. fitting more origins later gives the same forecasts as fitting them all at once
const La = E.prepare(seas, 12, null, [], 24); E.ensure(La, 48); const Lb = E.prepare(seas, 12, null, [], 48);
check("lazy fitting matches fitting all at once", La.lo === Lb.lo && Object.keys(Lb.fc).every(id => Object.keys(Lb.fc[id]).every(T => La.fc[id][T].join() === Lb.fc[id][T].join())), La.lo + " " + Lb.lo);

// 13. too little history to test the choice: the table still works, the pool test is skipped
const short = seas.slice(0, 60), Q = E.score(E.prepare(short, 12), { h: 6, test: 24 });
check("short history: no re-picked test, minimum length reported", Q.pool === null && Q.needN === 26 + 48 && fin(Q), Q.needN);

console.log(fails ? fails + " check(s) failed" : "all engine checks passed"); process.exit(fails ? 1 : 0);
