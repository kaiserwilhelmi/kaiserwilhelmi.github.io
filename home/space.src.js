/* Earth graphic shared by the home and About pages. The stars behind it are drawn by /theme.js, the site theme.
   This file is home/space.src.js; home/build.py adds the land grid and writes /space.js.

   The page needs: <div class="page"> holding <canvas id="sky"> and <canvas id="globe">, a header.site and, in each view,
   a section.intro with a <p>. <html data-view> says which view is showing: "hero" (Projects) or "about".
   A link with data-go="about" flies the Earth in to San Diego and then fades the About view in, without loading a page;
   data-go="hero" does the reverse. The address bar and the Back button follow along.
   The land is a half-degree grid from Natural Earth (public domain). The arcs between ports are decoration, not data. */
(function () {
"use strict";
const LAND = /*__LAND__*/null;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const rad = d => d * Math.PI / 180, clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const HOME = { lat: 32.72, lon: -117.16, name: "San Diego County, CA", pos: "32.7°N 117.2°W" };
const ZOOM = 2.3, FLY_MS = 1500;
const $ = id => document.getElementById(id);

/* ---------- land grid and the points drawn on it ---------- */
let cells = null;
function isLand(lat, lon) {
  if (!cells) { const b = atob(LAND.r); cells = new Uint8Array(LAND.w * LAND.h); let k = 0, v = 0, n = 0, sh = 0;
    for (let i = 0; i < b.length; i++) { const x = b.charCodeAt(i); n |= (x & 127) << sh; if (x & 128) { sh += 7; continue; } if (v) cells.fill(1, k, k + n); k += n; v ^= 1; n = 0; sh = 0; } }
  const r = Math.min(LAND.h - 1, Math.floor((90 - lat) * LAND.h / 180)), q = Math.floor(((lon + 540) % 360) * LAND.w / 360) % LAND.w;
  return cells[r * LAND.w + q];
}
const vec = (lat, lon) => [Math.cos(rad(lat)) * Math.sin(rad(lon)), Math.sin(rad(lat)), Math.cos(rad(lat)) * Math.cos(rad(lon))];
// evenly spaced points on the sphere (Fibonacci lattice), keeping the ones on land; `near` keeps only points within that angle of home
function lattice(R, near) {
  const N = Math.round(4 * Math.PI * R * R / 46), GA = Math.PI * (3 - Math.sqrt(5)), out = [], h = vec(HOME.lat, HOME.lon), lim = near ? Math.cos(near) : -2;
  for (let i = 0; i < N; i++) { const y = 1 - 2 * (i + 0.5) / N, lon = (i * GA) % (2 * Math.PI) - Math.PI, q = Math.sqrt(1 - y * y), x = q * Math.sin(lon), z = q * Math.cos(lon);
    if (x * h[0] + y * h[1] + z * h[2] < lim) continue;
    if (isLand(Math.asin(y) * 180 / Math.PI, lon * 180 / Math.PI)) out.push(x, y, z); }
  return new Float32Array(out);
}
const PORT = { sha: [31.2, 121.5], sin: [1.3, 103.8], rot: [51.9, 4.1], la: [33.7, -118.2], ny: [40.7, -74.0], hou: [29.7, -95.0], san: [-23.9, -46.3], dxb: [25.0, 55.1], yok: [35.4, 139.7], mum: [18.9, 72.9], dur: [-29.9, 31.0], syd: [-33.9, 151.2] };
const LANES = [["sha", "la"], ["rot", "ny"], ["sin", "rot"], ["sha", "sin"], ["hou", "rot"], ["san", "sha"], ["yok", "la"], ["dxb", "sin"], ["mum", "dxb"], ["dur", "mum"], ["syd", "sha"], ["san", "ny"]];
const ports = Object.values(PORT).map(p => vec(p[0], p[1]));
const lanes = LANES.map(([a, b], i) => { const A = vec(...PORT[a]), B = vec(...PORT[b]), w = Math.acos(clamp(A[0] * B[0] + A[1] * B[1] + A[2] * B[2], -1, 1)), n = 48, v = new Float32Array((n + 1) * 3);
  for (let k = 0; k <= n; k++) { const t = k / n, s1 = Math.sin((1 - t) * w) / Math.sin(w), s2 = Math.sin(t * w) / Math.sin(w), lift = 1 + (0.03 + 0.13 * w / Math.PI) * Math.sin(Math.PI * t);
    for (let d = 0; d < 3; d++) v[k * 3 + d] = (A[d] * s1 + B[d] * s2) * lift; }
  return { v, n, dur: 5200 + w * 2600, ph: (i * 0.37) % 1 }; });

/* ---------- the globe ---------- */
const G = { mode: "hero", k: 0, lon: rad(-72), tilt: rad(6), vel: 0, drag: null, on: true, fly: null, dirty: true };
let c, g, pageEl, pin, geo, coarse, dense, dpr = 1;

function layout() {
  c = $("globe"); if (!c || !LAND || getComputedStyle(c).display === "none") return false;
  pageEl = c.parentElement;
  const introEl = [...document.querySelectorAll(".intro")].find(e => e.offsetParent) || document.querySelector(".intro");
  const page = pageEl.getBoundingClientRect(), intro = introEl.getBoundingClientRect();
  const W = page.width, narrow = W < 760, R = narrow ? 190 : Math.min(310, Math.max(240, W * 0.235));
  const it = intro.top - page.top, cut = intro.bottom - page.top + 2, H = Math.max(200, cut + 30), top = 0;
  const wrapR = document.querySelector(".site").getBoundingClientRect().right - page.left, textR = introEl.querySelector("p").getBoundingClientRect().right - page.left;
  const cx = narrow ? W - 46 : wrapR - R * 0.56;
  const changed = !geo || geo.R !== R;
  geo = { W, H, top, cut, narrow, R, textR,
    it, hero: { cx, cy: it + (narrow ? 14 : 22) + R, R, tilt: rad(6) },
    about: { cx: narrow ? W - 72 : Math.max(textR + 110, wrapR - R * 1.12), cy: it + (narrow ? 44 : 150), R: R * ZOOM, tilt: rad(HOME.lat), lon: rad(HOME.lon) } };
  dpr = Math.min(2, devicePixelRatio || 1);
  c.style.cssText = `left:0;top:${top}px;width:${W}px;height:${H}px`; c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); g = c.getContext("2d");
  if (changed) { coarse = lattice(R); dense = null; }
  placePin(); G.dirty = true; return true;
}
function pose() {       // where the camera is now: the hero view, the San Diego view, or part-way between
  const a = geo.hero, b = geo.about, k = G.k, mix = (x, y) => x + (y - x) * k;
  return { cx: mix(a.cx, b.cx), cy: mix(a.cy, b.cy), R: a.R * Math.pow(ZOOM, k), lon: G.lon, tilt: G.tilt };
}
function placePin() {
  if (!pin) { pin = document.createElement("div"); pin.id = "globe-pin"; pin.setAttribute("aria-hidden", "true");
    pin.innerHTML = `<i></i><span><b>${HOME.name}</b>${HOME.pos}</span>`; pageEl.insertBefore(pin, c.nextSibling);
    const st = document.createElement("style");
    st.textContent = `#globe-pin{position:absolute;z-index:1;pointer-events:none;opacity:0;transition:opacity .5s;font:12px/1.35 "IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;color:#aab5c7;white-space:nowrap}
#globe-pin.show{opacity:1}
#globe-pin i{position:absolute;left:-4px;top:-4px;width:8px;height:8px;border-radius:50%;background:#f2faff;box-shadow:0 0 10px 2px rgba(124,199,242,.75)}
#globe-pin i::after{content:"";position:absolute;inset:-5px;border:1.5px solid #7cc7f2;border-radius:50%;opacity:.7}
#globe-pin span{position:absolute;top:-21px;left:28px;padding:3px 9px 4px;border-radius:5px;background:rgba(8,12,21,.72)}
#globe-pin.left span{left:auto;right:28px;text-align:right}
#globe-pin b{display:block;font:600 14px/1.3 "IBM Plex Sans",-apple-system,"Segoe UI",Arial,sans-serif;color:#eef2f8}
@keyframes dw-ping{from{transform:scale(1);opacity:.75}to{transform:scale(3.4);opacity:0}}
@media (prefers-reduced-motion:no-preference){#globe-pin.show i::after{animation:dw-ping 2.4s ease-out infinite}}`;
    document.head.appendChild(st); }
  pin.style.left = geo.about.cx + "px"; pin.style.top = (geo.top + geo.about.cy) + "px";
  pin.classList.toggle("left", geo.about.cx + 230 > geo.W);
  pin.classList.toggle("show", G.mode === "about" && !G.fly);
}

const out = new Float32Array(3);
function paint(t) {
  const { W, H, narrow, textR } = geo, P = pose(), X = P.cx, cy = P.cy, R = P.R, k = G.k;
  const sl = Math.sin(P.lon), cl = Math.cos(P.lon), stl = Math.sin(P.tilt), ctl = Math.cos(P.tilt);
  const proj = (x, y, z) => { const x1 = x * cl - z * sl, z1 = x * sl + z * cl; out[0] = x1; out[1] = y * ctl - z1 * stl; out[2] = y * stl + z1 * ctl; };
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  // atmosphere, then the night-blue sphere lit from the upper left
  let q = g.createRadialGradient(X, cy, R * 0.94, X, cy, R * 1.24); q.addColorStop(0, "rgba(96,170,255,.34)"); q.addColorStop(0.35, "rgba(70,130,240,.13)"); q.addColorStop(1, "rgba(60,110,220,0)");
  g.fillStyle = q; g.beginPath(); g.arc(X, cy, R * 1.24, 0, 6.3); g.fill();
  q = g.createRadialGradient(X - R * 0.42, cy - R * 0.5, R * 0.08, X, cy, R); q.addColorStop(0, "#132a52"); q.addColorStop(0.55, "#0b1832"); q.addColorStop(1, "#070c18");
  g.fillStyle = q; g.beginPath(); g.arc(X, cy, R, 0, 6.3); g.fill();
  q = g.createLinearGradient(X - R, cy - R, X + R * 0.5, cy + R * 0.4); q.addColorStop(0, "rgba(160,215,255,.85)"); q.addColorStop(0.55, "rgba(120,190,255,.16)"); q.addColorStop(1, "rgba(120,190,255,0)");
  g.strokeStyle = q; g.lineWidth = 1.2; g.beginPath(); g.arc(X, cy, R - 0.6, 0, 6.3); g.stroke();
  // land: the wide-view points fade out and the close-up points fade in as the camera moves in
  const fine = clamp((k - 0.2) / 0.6, 0, 1), LX = -0.52, LY = 0.62, LZ = 0.59;
  const dots = (pts, size, alpha, flat) => { if (alpha <= 0.01 || !pts) return; const B = [[], [], [], [], [], []];
    for (let i = 0; i < pts.length; i += 3) { proj(pts[i], pts[i + 1], pts[i + 2]); if (out[2] <= 0.02) continue;
      const sx = X + out[0] * R, sy = cy - out[1] * R; if (sy > H + 2 || sy < -2 || sx < -2 || sx > W + 2) continue;
      const lit = Math.max(0, out[0] * LX + out[1] * LY + out[2] * LZ), a = (0.3 + 0.7 * (lit + (0.75 - lit) * flat)) * (0.42 + 0.58 * out[2]);
      B[Math.min(5, a * 6 | 0)].push(sx, sy, size * (1.1 + 0.9 * out[2])); }
    g.fillStyle = "#93d4f8";
    B.forEach((b, j) => { g.globalAlpha = (0.16 + j * 0.15) * alpha; for (let i = 0; i < b.length; i += 3) g.fillRect(b[i] - b[i + 2] / 2, b[i + 1] - b[i + 2] / 2, b[i + 2], b[i + 2]); }); g.globalAlpha = 1; };
  if (k > 0 && !dense) dense = lattice(geo.R * ZOOM, rad(75));
  dots(coarse, Math.sqrt(R / geo.R), 1 - fine, k); dots(dense, R / (geo.R * ZOOM), fine, k);
  // latitude and longitude lines every 10 degrees, close-up only
  if (fine > 0.01) { g.strokeStyle = "rgba(124,199,242," + (0.09 * fine).toFixed(3) + ")"; g.lineWidth = 1; g.beginPath();
    const seg = (la, lo, first) => { const v = vec(la, lo); proj(v[0], v[1], v[2]); const sx = X + out[0] * R, sy = cy - out[1] * R, ok = out[2] > 0.05 && sx > -200 && sx < W + 200 && sy > -200 && sy < H + 200; if (ok && !first) g.lineTo(sx, sy); else g.moveTo(sx, sy); return !ok; };
    for (let la = -10; la <= 80; la += 10) { let f = true; for (let lo = -180; lo <= -40; lo += 2) f = seg(la, lo, f); }
    for (let lo = -180; lo <= -40; lo += 10) { let f = true; for (let la = -20; la <= 84; la += 2) f = seg(la, lo, f); }
    g.stroke(); }
  // ports and lanes (hidden in the close-up)
  const far = 1 - clamp(k / 0.6, 0, 1);
  if (far > 0.01) { g.lineCap = "round";
    for (const p of ports) { proj(p[0], p[1], p[2]); if (out[2] <= 0.05) continue; const px = X + out[0] * R, py = cy - out[1] * R;
      g.fillStyle = "rgba(190,230,255," + (0.14 * out[2] * far).toFixed(3) + ")"; g.beginPath(); g.arc(px, py, 5, 0, 6.3); g.fill();
      g.fillStyle = "rgba(225,243,255," + ((0.35 + 0.6 * out[2]) * far).toFixed(3) + ")"; g.beginPath(); g.arc(px, py, 1.7, 0, 6.3); g.fill(); }
    for (const ln of lanes) { const sx = [], sy = [], ok = [];
      for (let j = 0; j <= ln.n; j++) { proj(ln.v[j * 3], ln.v[j * 3 + 1], ln.v[j * 3 + 2]); sx.push(X + out[0] * R); sy.push(cy - out[1] * R); ok.push(out[2] > 0); }
      g.strokeStyle = "rgba(124,199,242," + (0.26 * far).toFixed(3) + ")"; g.lineWidth = 1; g.beginPath();
      for (let j = 1; j <= ln.n; j++) if (ok[j] && ok[j - 1]) { g.moveTo(sx[j - 1], sy[j - 1]); g.lineTo(sx[j], sy[j]); } g.stroke();
      if (reduce) continue;
      const u = ((t / ln.dur + ln.ph) % 1.7) * (ln.n + 9), h = Math.floor(u);            // one pulse per lane, with a rest between runs
      for (let j = Math.max(1, h - 8); j <= Math.min(ln.n, h); j++) if (ok[j] && ok[j - 1]) { g.strokeStyle = "rgba(226,244,255," + (0.9 * far * (1 - (h - j) / 9)).toFixed(3) + ")"; g.lineWidth = 1.6; g.beginPath(); g.moveTo(sx[j - 1], sy[j - 1]); g.lineTo(sx[j], sy[j]); g.stroke(); }
      if (h >= 0 && h <= ln.n && ok[h]) { g.fillStyle = "rgba(242,250,255," + far.toFixed(3) + ")"; g.beginPath(); g.arc(sx[h], sy[h], 1.9, 0, 6.3); g.fill(); } } }
  // fade into the page below, and behind the text where the two overlap
  g.globalCompositeOperation = "destination-in";
  q = g.createLinearGradient(0, H - 150, 0, H - 30); q.addColorStop(0, "#000"); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.fillRect(0, 0, W, H);
  q = g.createLinearGradient(0, 0, 0, geo.it - 6); q.addColorStop(0, "rgba(0,0,0,0)"); q.addColorStop(1, "#000"); g.fillStyle = q; g.fillRect(0, 0, W, H);
  const hx = geo.hero.cx, hr = geo.R;
  if (narrow) { q = g.createLinearGradient(hx - hr * 1.1, 0, hx + hr * 0.25, 0); q.addColorStop(0, "rgba(0,0,0,.12)"); q.addColorStop(1, "rgba(0,0,0,.8)"); g.fillStyle = q; g.fillRect(0, 0, W, H); }
  else if (textR > X - R) { const s = clamp((textR - (X - R)) / 90, 0, 1); q = g.createLinearGradient(textR - 70 - 260 * k, 0, textR + 70 + 30 * k, 0); q.addColorStop(0, "rgba(0,0,0," + (1 - 0.86 * s).toFixed(3) + ")"); q.addColorStop(1, "#000"); g.fillStyle = q; g.fillRect(0, 0, W, H); }
  g.globalCompositeOperation = "source-over";
}

// move the camera between the two views; resolves when it arrives
function fly(to, ms) {
  if (!geo) return Promise.resolve();
  const k1 = to === "about" ? 1 : 0, lon1 = to === "about" ? geo.about.lon : G.lon, tilt1 = to === "about" ? geo.about.tilt : geo.hero.tilt;
  pin.classList.remove("show"); G.vel = 0; G.drag = null;
  if (reduce || !ms) { G.k = k1; G.lon = lon1; G.tilt = tilt1; G.mode = to; G.fly = null; G.dirty = true; placePin(); paint(0); return Promise.resolve(); }
  let dl = (lon1 - G.lon) % (2 * Math.PI); if (dl > Math.PI) dl -= 2 * Math.PI; if (dl < -Math.PI) dl += 2 * Math.PI;
  return new Promise(done => { G.fly = { t0: 0, ms, k0: G.k, k1, lon0: G.lon, dl, tilt0: G.tilt, tilt1, to, done }; });
}
function frame(t) {
  G.raf = requestAnimationFrame(frame);
  if (!geo || document.hidden) return;
  const f = G.fly;
  if (f) { if (!f.t0) f.t0 = t; const u = clamp((t - f.t0) / f.ms, 0, 1), e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    G.k = f.k0 + (f.k1 - f.k0) * e; G.lon = f.lon0 + f.dl * e; G.tilt = f.tilt0 + (f.tilt1 - f.tilt0) * e; paint(t);
    if (u === 1) { G.fly = null; G.mode = f.to; G.last = t; placePin(); f.done(); } return; }
  if (G.mode === "about") { if (G.dirty) { G.dirty = false; paint(t); } return; }        // the close-up is a still picture
  if (!G.on || t - (G.last || 0) < 30) return;
  const dt = Math.min(100, t - (G.last || t)); G.last = t;
  if (reduce) { if (G.dirty) { G.dirty = false; paint(0); } return; }
  if (!G.drag) { G.lon += G.vel; G.vel *= 0.94; if (Math.abs(G.vel) < 0.0004) G.lon -= dt * 2 * Math.PI / 170000; }   // coast after a drag, then one turn in about three minutes
  paint(t);
}
function wire() {
  const inside = e => { if (G.mode !== "hero" || G.fly) return false; const b = pageEl.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top, h = geo.hero;
    return y < geo.cut && Math.hypot(x - h.cx, y - geo.top - h.cy) < h.R && !e.target.closest("a, button, h1, p, select, input"); };
  pageEl.addEventListener("pointerdown", e => { if (e.pointerType === "touch" || e.button !== 0 || !inside(e)) return; G.drag = { x: e.clientX, y: e.clientY }; G.vel = 0; pageEl.setPointerCapture(e.pointerId); pageEl.style.cursor = "grabbing"; e.preventDefault(); });
  pageEl.addEventListener("pointermove", e => { if (!G.drag) { if (e.pointerType !== "touch") pageEl.style.cursor = inside(e) ? "grab" : ""; return; }
    const dx = e.clientX - G.drag.x, dy = e.clientY - G.drag.y; G.drag = { x: e.clientX, y: e.clientY }; G.lon -= dx / geo.R; G.vel = -dx / geo.R; G.tilt = clamp(G.tilt + dy / geo.R, -0.5, 0.9); G.dirty = true; });
  const end = () => { if (G.drag) { G.drag = null; pageEl.style.cursor = ""; } }; pageEl.addEventListener("pointerup", end); pageEl.addEventListener("pointercancel", end);
  if ("IntersectionObserver" in window) new IntersectionObserver(es => { G.on = es[0].isIntersecting; }).observe(c);
  let rt, lastW = innerWidth; addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; clearTimeout(rt); rt = setTimeout(() => { if (layout()) paint(0); }, 150); });
}

/* ---------- switching between the Projects view and the About view ---------- */
const root = document.documentElement, TITLE = { hero: "Dawson Wilhelmi · Projects", about: "Dawson Wilhelmi · About" };
const view = () => root.dataset.view === "about" ? "about" : "hero";
const want = () => /^\/about\/?$/.test(location.pathname) ? "about" : "hero";
const wait = ms => new Promise(r => setTimeout(r, ms));
let busy = false, next = null;       // next: a view asked for while a switch was under way
function show(v) {       // swap which view is in the page; the caller handles the fading
  root.dataset.view = v; document.title = TITLE[v];
  document.querySelectorAll("a[data-go]").forEach(a => { if (a.dataset.go === v && a.closest("nav")) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  scrollTo(0, 0); if (api.onview) api.onview(v); if (geo && layout()) paint(performance.now());
}
async function go(to, push) {
  if (to !== "about") to = "hero";
  if (push && !api.noHistory && to !== want()) { try { history.pushState({ view: to }, "", to === "about" ? "/about/" : "/"); } catch (err) {} }
  if (busy) { next = to; return; }          // picked up when the current switch ends
  if (to === view()) return;
  busy = true; next = null;
  const hasGlobe = !!geo, quick = reduce || !hasGlobe;
  if (pageEl) pageEl.classList.add("leaving");                      // the showing view fades out
  if (to === "about") {
    if (scrollY > 0) scrollTo({ top: 0, behavior: quick ? "auto" : "smooth" });
    if (hasGlobe) await fly("about", quick ? 0 : FLY_MS);          // the Earth turns and closes in on San Diego, the pin lands
    if (!quick) await wait(250);
    show("about");
  } else {
    if (!quick) await wait(450);
    show("hero");
    if (hasGlobe) fly("hero", quick ? 0 : 1300);                    // the Projects view fades in while the Earth pulls back
  }
  if (pageEl) { void pageEl.offsetWidth; pageEl.classList.remove("leaving"); }
  const m = document.getElementById("main"); if (m && push) m.focus({ preventScroll: true });
  if (!quick) await wait(to === "about" ? 450 : 1300);
  busy = false;
  const then = api.noHistory ? next : want();                       // a second click, Back or Forward arrived mid-move
  if (then && then !== view()) go(then, false);
}

const api = window.DWSpace = {
  init() { pageEl = document.querySelector(".page"); const ok = layout();
    addEventListener("click", e => { const a = e.target.closest && e.target.closest("a[data-go]"); if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault(); e.stopImmediatePropagation(); go(a.dataset.go, true); }, true);
    addEventListener("popstate", () => go(want(), false));
    if (!ok) return;
    fly(view(), 0); wire(); G.raf = requestAnimationFrame(frame); },
  fly, go, layout() { if (layout()) paint(0); }, onview: null, noHistory: false,
  get mode() { return G.mode; }, get view() { return view(); }
};
})();
