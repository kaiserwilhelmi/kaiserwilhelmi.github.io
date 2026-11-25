/* Engine checks (Node, no browser): flat histories, non-numbers, filled values that must not be
 * scored, NaN-safe ranking, MASE unchanged when the series is rescaled, complete-origin scoring,
 * no look-ahead in the re-picked pool, the size of the Diebold-Mariano test, Holm, lazy fitting,
 * chunked (worker) fitting, conformal bounds, and forecast ranges (no look-ahead, calibration).
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

// 14. background fitting: fitRange + merge (the worker's job) and futures() give the same numbers
const W1 = E.skeleton(seas, 12, []), Wl = E.loFor(W1, 48);
E.merge(W1, E.fitRange(seas, 12, Wl + 20, W1.lo), Wl + 20); E.merge(W1, E.fitRange(seas, 12, Wl, Wl + 20), Wl);
const fu = E.futures(seas, 12);
check("fitting in chunks (as the worker does) matches prepare()", W1.lo === Lb.lo && Object.keys(Lb.fc).every(id => Object.keys(Lb.fc[id]).every(T => W1.fc[id][T].join() === Lb.fc[id][T].join())));
check("futures() matches prepare()", Object.keys(Lb.fut).every(id => fu[id].f.join() === Lb.fut[id].f.join()));

// 15. conformal bounds: the right order statistics, and flagged when there are too few errors
const z48 = Array.from({ length: 48 }, (_, i) => i), cb = L => E.confBounds(z48, L);
check("conformal bounds, 48 errors: 80% = 4th and 45th, 95% = smallest and largest", cb(0.8).lo === 3 && cb(0.8).hi === 44 && cb(0.95).lo === 0 && cb(0.95).hi === 47 && cb(0.95).ok, JSON.stringify([cb(0.8), cb(0.95)]));
const z19 = Array.from({ length: 19 }, (_, i) => i);
check("conformal bounds, 19 errors: 80% = 2nd and 18th; 95% flagged as too few", E.confBounds(z19, 0.8).lo === 1 && E.confBounds(z19, 0.8).hi === 17 && !E.confBounds(z19, 0.95).ok);

// 16. ranges: no look-ahead, and the check counts what it says
const seasL = Array.from({ length: 150 }, (_, i) => 100 + 10 * Math.sin(2 * Math.PI * i / 12) + i * 0.5 + 3 * Math.sin(i * 1.7));
const R0 = E.prepare(seasL, 12, null, [], 2 * 24 + 6 + 47), rg0 = E.ranges(R0, { h: 6, test: 24, kind: "pool", levels: [0.5, 0.8, 0.95] });
const TT = rg0.check[30].T, Rp = Object.assign({}, R0, { y: seasL.map((v, i) => i >= TT ? v * 1.5 + 40 : v) });
const rg1 = E.ranges(Rp, { h: 6, test: 24, kind: "pool", levels: [0.5, 0.8, 0.95] });
const rowsAt = g => g.check.filter(c => c.T <= TT).map(c => [c.T, c.k, c.f, c.lo.join(), c.hi.join()].join("|")).join(";");
check("ranges at origin T ignore every value from T on", rowsAt(rg0) === rowsAt(rg1) && rowsAt(rg0).length > 0);
const ins = rg0.check.filter(c => c.y >= c.lo[1] && c.y <= c.hi[1]).length;
check("check: 80% coverage = share of actuals inside", Math.abs(ins / rg0.check.length - rg0.cover[0.8]) < 1e-12 && rg0.check.length === 19 * 6, ins + "/" + rg0.check.length);
check("with 2 x window + h + 47 origins fitted, every range and every check uses 48 errors", rg0.future.every(f => f && f.n === 48) && rg0.nCheck === 19 * 6 && rg0.check.every(c => c.n === 48), rg0.future.map(f => f && f.n).join());
const Rs = E.prepare(seas.slice(0, 80), 12), rgs = E.ranges(Rs, { h: 6, test: 24, kind: "pool", levels: [0.8] });
check("short history: ranges with fewer errors, or none, never an error", rgs === null || rgs.future.every(f => f === null || f.n >= E.MINCAL), rgs && rgs.future.map(f => f && f.n).join());

// 17. calibration on a random walk (naive is the right model): 80% ranges hold about 80% of the time
let hits = 0, tot = 0;
for (let rep = 0; rep < 400; rep++) {
  const rw = [100]; for (let i = 1; i < 120; i++) rw.push(rw[i - 1] + gauss());
  const Pn = { y: rw, m: 1, lo: 2, skip: {}, fc: { naive: {} } };
  for (let T = 2; T < 120; T++) Pn.fc.naive[T] = Array(12).fill(rw[T - 1]);
  const g = E.ranges(Pn, { h: 6, test: 24, kind: "naive", levels: [0.8] });
  hits += g.cover[0.8] * g.nCheck; tot += g.nCheck;
}
check("random walk: naive 80% ranges hold 78% to 86% of the time", hits / tot > 0.78 && hits / tot < 0.86, (100 * hits / tot).toFixed(1) + "%");

// 18. a series that never goes below zero gets ranges floored at zero; coverage is unchanged
// (shifting the series down by 1000 gives the same errors, no floor, and must give the same coverage)
function naiveP(y) { const P = { y, m: 1, lo: 2, skip: {}, fc: { naive: {} } }; for (let T = 2; T < y.length; T++) P.fc.naive[T] = Array(12).fill(y[T - 1]); return P; }
const pos = []; for (let i = 0; i < 120; i++) pos.push(Math.abs(3 * gauss()));
const gp = E.ranges(naiveP(pos), { h: 6, test: 24, kind: "naive", levels: [0.5, 0.8, 0.95] });
const gs = E.ranges(naiveP(pos.map(v => v - 1000)), { h: 6, test: 24, kind: "naive", levels: [0.5, 0.8, 0.95] });
const clipped = gp.check.filter(c => c.lo.some(v => v === 0)).length;
check("non-negative series: ranges floored at zero, coverage unchanged", gp.floor === 0 && gs.floor === null && clipped > 0 &&
  gp.check.every(c => c.p50 >= 0 && c.lo.every(v => v >= 0) && c.hi.every(v => v >= 0)) &&
  [0.5, 0.8, 0.95].every(L => gp.cover[L] === gs.cover[L]) && gp.nOrigins === 19, clipped + " clipped; " + [0.5, 0.8, 0.95].map(L => gp.cover[L] + "/" + gs.cover[L]).join(" "));

// 19. Phase 4 fits: on a random walk SES puts nearly all weight on the last value (the old grid capped
// alpha at 0.95); the continuous fit never ends worse than the grid it starts from; tree count is on the menu
const rw2 = [100]; for (let i = 1; i < 150; i++) rw2.push(rw2[i - 1] + gauss());
const sesM = E.METHODS.find(d => d.id === "ses"), gbmM = E.METHODS.find(d => d.id === "gbm"), holtM = E.METHODS.find(d => d.id === "holt");
let over = 0, maxA = 0;
for (let rep = 0; rep < 40; rep++) { const w = [100]; for (let i = 1; i < 120; i++) w.push(w[i - 1] + gauss()); const a = sesM.fn(w, 1, 1).params.alpha; if (a > 0.95) over++; maxA = Math.max(maxA, a); }
check("random walks: SES alpha often above the old 0.95 cap, never above 0.9999", over >= 12 && maxA <= 0.9999, over + "/40 above 0.95, max " + maxA);
const hp4 = holtM.fn(rw2, 1, 1).params;
check("Holt weights inside [1e-4, 0.9999]", hp4.alpha >= 1e-4 && hp4.alpha <= 0.9999 && hp4.beta >= 1e-4 && hp4.beta <= 0.9999, JSON.stringify(hp4));
const tr = gbmM.fn(rw2, 1, 1).params.trees;
check("boosted trees: tree count chosen from 25/50/100/150", [25, 50, 100, 150].includes(tr), tr);

// 20. Phase 5, intermittent demand. Classification by Syntetos, Boylan & Croston (2005).
const dp = E.demandPattern([0, 0, 4, 0, 0, 4, 0, 0, 4, 0, 0, 4]);
check("demand pattern: ADI and CV2 by hand", Math.abs(dp.adi - 3) < 1e-12 && dp.cv2 === 0 && dp.kind === "intermittent" && dp.intermittent, JSON.stringify(dp));
const lp = E.demandPattern([0, 1, 0, 0, 20, 0, 0, 2, 0, 30]);
check("demand pattern: lumpy when sizes vary a lot", lp.kind === "lumpy" && lp.intermittent, JSON.stringify(lp));
check("demand pattern: smooth or negative series are not intermittent", !E.isIntermittent(seas) && !E.isIntermittent([0, -1, 0, 0, 3, 0, 0, 2]) && E.demandPattern([1, -2]) === null);
// Croston on perfectly regular demand (5 every 3rd period) forecasts the rate 5/3; SBA is lower by 1 - a/2
const reg = []; for (let i = 0; i < 60; i++) reg.push(i % 3 === 2 ? 5 : 0);
const cM = E.METHODS.find(d => d.id === "croston"), sM = E.METHODS.find(d => d.id === "sba"), tM = E.METHODS.find(d => d.id === "tsb");
const cr = cM.fn(reg, 3, 1), sb = sM.fn(reg, 3, 1);
check("Croston: regular demand gives the true rate", Math.abs(cr.f[0] - 5 / 3) < 1e-3 && cr.f.every(v => v === cr.f[0]), cr.f[0]);
check("SBA: at or below Croston, by the 1 - a/2 factor", sb.f[0] <= cr.f[0] + 1e-12 && sb.params.gap_alpha <= 1 && sb.params.size_alpha >= 1e-4, sb.f[0] + " " + JSON.stringify(sb.params));
// TSB lets the forecast fall when orders stop; Croston cannot change until the next order
const dead = []; for (let i = 0; i < 80; i++) dead.push(i < 60 && i % 2 === 0 ? 6 : 0);
const tf = tM.fn(dead, 1, 1).f[0], cf = cM.fn(dead, 1, 1).f[0];
check("TSB: forecast falls after 20 periods without demand, below Croston", tf < cf, "tsb " + tf + ", croston " + cf);
// in intermittent mode: the three methods join, ranking is by RMSE, every forecast is >= 0
const spikes = []; let sd = 11; const rr = () => (sd = (sd * 16807) % 2147483647) / 2147483647;
for (let i = 0; i < 120; i++) spikes.push(rr() < 0.3 ? 1 + Math.round(rr() * 9) : 0);
const IP = E.prepare(spikes, 1), ir = E.score(IP, { h: 3, test: 24 });
const iids = ir.results.map(x => x.id);
check("intermittent series: Croston, SBA and TSB join, ranked by RMSE", ["croston", "sba", "tsb"].every(i => iids.includes(i)) && ir.rankBy === "RMSE" &&
  E.rank(ir.results, "RMSE").every((x, i, a) => !i || a[i - 1].metrics.RMSE <= x.metrics.RMSE), ir.rankBy);
check("intermittent series: no forecast below zero", Object.keys(IP.fc).every(id => Object.values(IP.fc[id]).every(f => f.every(v => v >= 0))) && ir.results.every(x => x.future.every(v => v >= 0)));
check("smooth series: no intermittent methods, ranked by MASE", !E.prepare(seas, 12).meths.some(d => d.intermittent) && E.score(E.prepare(seas, 12), { h: 6, test: 24 }).rankBy === "MASE");

console.log(fails ? fails + " check(s) failed" : "all engine checks passed"); process.exit(fails ? 1 : 0);
