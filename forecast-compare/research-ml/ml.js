/* Prototype: Theta + machine-learning forecasters (ridge, gradient-boosted trees, MLP).
 * Same interface as engine methods: fn(y, h, m) -> { f: [...], params }. Deterministic. */
"use strict";
function mean(a) { let s = 0; for (const x of a) s += x; return s / a.length; }

// ---------- Theta (Assimakopoulos & Nikolopoulos 2000; Hyndman & Billah 2003) ----------
function acf(y, k) { const mu = mean(y); let num = 0, den = 0; for (let t = 0; t < y.length; t++) { den += (y[t] - mu) ** 2; if (t >= k) num += (y[t] - mu) * (y[t - k] - mu); } return num / den; }
function seasonalTest(y, m) { // 90% test used in the M3/M4 Theta benchmark
  if (m <= 1 || y.length < 3 * m) return false;
  let s = 0; for (let k = 1; k < m; k++) s += acf(y, k) ** 2;
  return Math.abs(acf(y, m)) > 1.645 * Math.sqrt((1 + 2 * s) / y.length);
}
function classicalIndex(y, m, mult) { // centred moving-average decomposition
  const n = y.length, tr = new Array(n).fill(null);
  const half = Math.floor(m / 2);
  for (let t = half; t < n - half; t++) {
    let s = 0;
    if (m % 2 === 0) { for (let j = -half; j <= half; j++) s += (Math.abs(j) === half ? 0.5 : 1) * y[t + j]; s /= m; }
    else { for (let j = -half; j <= half; j++) s += y[t + j]; s /= m; }
    tr[t] = s;
  }
  const sums = new Array(m).fill(0), cnt = new Array(m).fill(0);
  for (let t = 0; t < n; t++) if (tr[t] !== null) { sums[t % m] += mult ? y[t] / tr[t] : y[t] - tr[t]; cnt[t % m]++; }
  let idx = sums.map((s, i) => s / cnt[i]);
  const c = mean(idx); idx = idx.map(v => mult ? v / c : v - c);
  return idx;
}
function theta(y, h, m) {
  const n = y.length, seas = seasonalTest(y, m), mult = y.every(v => v > 0);
  const idx = seas ? classicalIndex(y, m, mult) : null;
  const x = seas ? y.map((v, t) => mult ? v / idx[t % m] : v - idx[t % m]) : y.slice();
  // OLS slope of the deseasonalised series on time
  const tm = (n - 1) / 2, xm = mean(x); let sxy = 0, sxx = 0;
  for (let t = 0; t < n; t++) { sxy += (t - tm) * (x[t] - xm); sxx += (t - tm) ** 2; }
  const b0 = sxy / sxx;
  // SES alpha by fine grid (0.01..0.99)
  let best = null;
  for (let i = 1; i <= 99; i++) {
    const a = i / 100; let l = x[0], sse = 0;
    for (let t = 1; t < n; t++) { const e = x[t] - l; sse += e * e; l += a * e; }
    if (!best || sse < best.sse) best = { sse, l, a };
  }
  const a = best.a, f = [];
  for (let k = 1; k <= h; k++) {
    let v = best.l + 0.5 * b0 * ((1 - Math.pow(1 - a, n)) / a + k - 1);
    if (seas) v = mult ? v * idx[(n + k - 1) % m] : v + idx[(n + k - 1) % m];
    f.push(v);
  }
  return { f, params: { alpha: a, seasonal: seas } };
}

// ---------- shared ML set-up: learn the next change from recent changes ----------
function lagsFor(m) { const L = []; const p = m > 1 ? Math.min(m, 13) : 6; for (let i = 1; i <= p; i++) L.push(i); if (m > 13) L.push(m); return L; }
function design(y, m) {
  const d = []; for (let t = 1; t < y.length; t++) d.push(y[t] - y[t - 1]);
  const L = lagsFor(m), maxL = Math.max(...L);
  const sd = Math.sqrt(mean(d.map(v => v * v))) || 1;
  const z = d.map(v => v / sd), X = [], Y = [];
  for (let t = maxL; t < z.length; t++) { X.push(L.map(l => z[t - l])); Y.push(z[t]); }
  return { z, X, Y, L, sd };
}
function recursive(y, h, D, predict) {
  const z = D.z.slice(), f = []; let last = y[y.length - 1];
  for (let k = 0; k < h; k++) {
    const x = D.L.map(l => z[z.length - l]), dz = predict(x);
    z.push(dz); last += dz * D.sd; f.push(last);
  }
  return f;
}
function solve(A, b) { const n = b.length, M = A.map((r, i) => r.concat([b[i]]));
  for (let c = 0; c < n; c++) { let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r; [M[c], M[p]] = [M[p], M[c]];
    for (let r = c + 1; r < n; r++) { const f = M[r][c] / M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; } }
  const x = new Array(n); for (let i = n - 1; i >= 0; i--) { let s = M[i][n]; for (let j = i + 1; j < n; j++) s -= M[i][j] * x[j]; x[i] = s / M[i][i]; } return x; }

// ---------- ridge regression on lags (AR model with shrinkage) ----------
function ridgeFit(X, Y, lam) {
  const p = X[0].length + 1, A = [], b = new Array(p).fill(0);
  for (let i = 0; i < p; i++) A.push(new Array(p).fill(0));
  X.forEach((r, i) => { const x = [1].concat(r); for (let a = 0; a < p; a++) { b[a] += x[a] * Y[i]; for (let c = 0; c < p; c++) A[a][c] += x[a] * x[c]; } });
  for (let a = 1; a < p; a++) A[a][a] += lam;
  return solve(A, b);
}
function ridge(y, h, m) {
  const D = design(y, m);
  // lambda by last-20% holdout, from a small grid
  const nv = Math.max(4, Math.floor(D.X.length * 0.2)), Xt = D.X.slice(0, -nv), Yt = D.Y.slice(0, -nv);
  let bestL = 1, bestE = Infinity;
  for (const lam of [0.1, 1, 10, 100]) {
    const w = ridgeFit(Xt, Yt, lam); let e = 0;
    for (let i = D.X.length - nv; i < D.X.length; i++) { let p = w[0]; D.X[i].forEach((v, j) => p += w[j + 1] * v); e += (p - D.Y[i]) ** 2; }
    if (e < bestE) { bestE = e; bestL = lam; }
  }
  const w = ridgeFit(D.X, D.Y, bestL);
  return { f: recursive(y, h, D, x => { let p = w[0]; x.forEach((v, j) => p += w[j + 1] * v); return p; }), params: { lambda: bestL } };
}

// ---------- gradient-boosted trees (Friedman 2001), depth-2, squared loss ----------
function gbm(y, h, m) {
  const D = design(y, m), X = D.X, Y = D.Y, n = X.length, p = X[0].length;
  const T = 150, lr = 0.05, minLeaf = Math.max(3, Math.floor(n / 20));
  const pred = new Array(n).fill(mean(Y)), base = pred[0], trees = [];
  const order = []; for (let j = 0; j < p; j++) order.push([...Array(n).keys()].sort((a, b) => X[a][j] - X[b][j] || a - b));
  function bestSplit(idxSet, r) {
    let best = null; const inSet = new Uint8Array(n); idxSet.forEach(i => inSet[i] = 1);
    const tot = idxSet.reduce((s, i) => s + r[i], 0), N = idxSet.length;
    for (let j = 0; j < p; j++) {
      let sl = 0, nl = 0;
      const ord = order[j].filter(i => inSet[i]);
      for (let k = 0; k < ord.length - 1; k++) {
        sl += r[ord[k]]; nl++;
        if (nl < minLeaf || N - nl < minLeaf) continue;
        if (X[ord[k]][j] === X[ord[k + 1]][j]) continue;
        const gain = sl * sl / nl + (tot - sl) * (tot - sl) / (N - nl);
        if (!best || gain > best.gain) best = { gain, j, thr: (X[ord[k]][j] + X[ord[k + 1]][j]) / 2 };
      }
    }
    return best;
  }
  function leafVal(idx, r) { return idx.length ? idx.reduce((s, i) => s + r[i], 0) / idx.length : 0; }
  const all = [...Array(n).keys()];
  for (let t = 0; t < T; t++) {
    const r = Y.map((v, i) => v - pred[i]);
    const s0 = bestSplit(all, r); if (!s0) break;
    const L = all.filter(i => X[i][s0.j] <= s0.thr), R = all.filter(i => X[i][s0.j] > s0.thr);
    const node = { j: s0.j, thr: s0.thr, kids: [L, R].map(set => {
      const s = bestSplit(set, r);
      if (!s) return { v: leafVal(set, r) };
      const a = set.filter(i => X[i][s.j] <= s.thr), b = set.filter(i => X[i][s.j] > s.thr);
      return { j: s.j, thr: s.thr, l: leafVal(a, r), r: leafVal(b, r) };
    }) };
    const ev = x => { const k = node.kids[x[node.j] <= node.thr ? 0 : 1]; return "v" in k ? k.v : (x[k.j] <= k.thr ? k.l : k.r); };
    trees.push(ev);
    for (let i = 0; i < n; i++) pred[i] += lr * ev(X[i]);
  }
  return { f: recursive(y, h, D, x => { let s = base; for (const ev of trees) s += lr * ev(x); return s; }), params: { trees: trees.length } };
}

// ---------- small neural net, ensemble of 5 (as in NNAR, Hyndman & Athanasopoulos ch. 12) ----------
function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function mlpOne(X, Y, seed, H, epochs) {
  const p = X[0].length, R = rng(seed), n = X.length;
  const W1 = [], b1 = new Array(H).fill(0), W2 = [], decay = 1e-3;
  for (let k = 0; k < H; k++) { W1.push([]); for (let j = 0; j < p; j++) W1[k].push((R() * 2 - 1) / Math.sqrt(p)); W2.push((R() * 2 - 1) / Math.sqrt(H)); }
  let b2 = 0;
  const params = () => [W1, b1, W2];
  // Adam, full batch
  const m1 = { W1: W1.map(r => r.map(() => 0)), b1: b1.map(() => 0), W2: W2.map(() => 0), b2: 0 }, v1 = JSON.parse(JSON.stringify(m1));
  const lr = 0.01, B1 = 0.9, B2 = 0.999, eps = 1e-8;
  const hid = new Array(H);
  for (let ep = 1; ep <= epochs; ep++) {
    const gW1 = W1.map(r => r.map(() => 0)), gb1 = new Array(H).fill(0), gW2 = new Array(H).fill(0); let gb2 = 0;
    for (let i = 0; i < n; i++) {
      const x = X[i];
      for (let k = 0; k < H; k++) { let s = b1[k]; for (let j = 0; j < p; j++) s += W1[k][j] * x[j]; hid[k] = Math.tanh(s); }
      let o = b2; for (let k = 0; k < H; k++) o += W2[k] * hid[k];
      const e = 2 * (o - Y[i]) / n; gb2 += e;
      for (let k = 0; k < H; k++) { gW2[k] += e * hid[k]; const g = e * W2[k] * (1 - hid[k] * hid[k]); gb1[k] += g; for (let j = 0; j < p; j++) gW1[k][j] += g * x[j]; }
    }
    const c1 = 1 - Math.pow(B1, ep), c2 = 1 - Math.pow(B2, ep);
    const upd = (val, g, mo, ve) => { mo = B1 * mo + (1 - B1) * g; ve = B2 * ve + (1 - B2) * g * g; return [val - lr * (mo / c1) / (Math.sqrt(ve / c2) + eps), mo, ve]; };
    for (let k = 0; k < H; k++) {
      for (let j = 0; j < p; j++) { const r = upd(W1[k][j], gW1[k][j] + decay * W1[k][j], m1.W1[k][j], v1.W1[k][j]); W1[k][j] = r[0]; m1.W1[k][j] = r[1]; v1.W1[k][j] = r[2]; }
      let r = upd(b1[k], gb1[k], m1.b1[k], v1.b1[k]); b1[k] = r[0]; m1.b1[k] = r[1]; v1.b1[k] = r[2];
      r = upd(W2[k], gW2[k] + decay * W2[k], m1.W2[k], v1.W2[k]); W2[k] = r[0]; m1.W2[k] = r[1]; v1.W2[k] = r[2];
    }
    const r = upd(b2, gb2, m1.b2, v1.b2); b2 = r[0]; m1.b2 = r[1]; v1.b2 = r[2];
  }
  return x => { let o = b2; for (let k = 0; k < H; k++) { let s = b1[k]; for (let j = 0; j < x.length; j++) s += W1[k][j] * x[j]; o += W2[k] * Math.tanh(s); } return o; };
}
function mlp(y, h, m) {
  const D = design(y, m), nets = [];
  for (let s = 1; s <= 5; s++) nets.push(mlpOne(D.X, D.Y, s * 7919, 6, 300));
  return { f: recursive(y, h, D, x => nets.reduce((a, net) => a + net(x), 0) / nets.length), params: { nets: 5, hidden: 6 } };
}

module.exports = { theta, ridge, gbm, mlp, seasonalTest };
