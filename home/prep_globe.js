// Builds land.json: a half-degree land/sea grid for the Earth graphic on the home and About pages.
// Source: Natural Earth 1:50m land (public domain), as packaged in npm world-atlas@2.0.2 (land-50m.json).
//   node prep_globe.js path/to/land-50m.json
// The grid is stored as run lengths (sea, land, sea, ...) along the rows from 90N, as base64 varints.
const fs = require("fs"), path = require("path");
const src = process.argv[2]; if (!src) { console.error("usage: node prep_globe.js land-50m.json"); process.exit(1); }
const topo = JSON.parse(fs.readFileSync(src, "utf8")), { scale, translate } = topo.transform;
const arcs = topo.arcs.map(a => { let x = 0, y = 0; return a.map(([dx, dy]) => [(x += dx) * scale[0] + translate[0], (y += dy) * scale[1] + translate[1]]); });
const ring = idx => { const out = []; for (const i of idx) { const a = i < 0 ? arcs[~i].slice().reverse() : arcs[i]; out.push(...(out.length ? a.slice(1) : a)); } return out; };
const rings = [];
const walk = g => { if (g.type === "GeometryCollection") g.geometries.forEach(walk);
  else if (g.type === "Polygon") g.arcs.forEach(r => rings.push(ring(r)));
  else if (g.type === "MultiPolygon") g.arcs.forEach(p => p.forEach(r => rings.push(ring(r)))); };
walk(topo.objects.land);
const W = 720, H = 360, bits = new Uint8Array(W * H / 8); let land = 0;
for (let r = 0; r < H; r++) { const lat = 90 - (r + 0.5) * 180 / H, xs = [];
  for (const R of rings) for (let i = 0, j = R.length - 1; i < R.length; j = i++) { const [x1, y1] = R[i], [x2, y2] = R[j];
    if ((y1 > lat) !== (y2 > lat)) xs.push(x1 + (lat - y1) / (y2 - y1) * (x2 - x1)); }
  xs.sort((a, b) => a - b);
  for (let c = 0; c < W; c++) { const lon = -180 + (c + 0.5) * 360 / W; let n = 0; for (const x of xs) if (x < lon) n++; else break;
    if (n & 1) { const k = r * W + c; bits[k >> 3] |= 1 << (k & 7); land++; } } }
const bit = k => bits[k >> 3] >> (k & 7) & 1, runs = []; let cur = 0, len = 0;
for (let k = 0; k < W * H; k++) { if (bit(k) === cur) len++; else { runs.push(len); cur ^= 1; len = 1; } } runs.push(len);
const bytes = []; for (let n of runs) { while (n > 127) { bytes.push(n & 127 | 128); n >>= 7; } bytes.push(n); }
fs.writeFileSync(path.join(__dirname, "land.json"), JSON.stringify({ w: W, h: H, r: Buffer.from(bytes).toString("base64") }));
console.log(runs.length, "runs,", bytes.length, "bytes");
console.log("land.json", (land / (W * H) * 100).toFixed(1) + "% of cells are land;", rings.length, "rings");
// quick look in the terminal
for (let r = 0; r < H; r += 12) { let s = ""; for (let c = 0; c < W; c += 6) { const k = r * W + c; s += bits[k >> 3] >> (k & 7) & 1 ? "#" : "."; } console.log(s); }
