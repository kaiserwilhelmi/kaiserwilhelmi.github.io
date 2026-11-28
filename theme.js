/* Star backdrop for every page on dawsonwilhelmi.com (one copy, shared by the home page and the tool pages).

   Load with  <script src="/theme.js" defer></script>.  It draws into <canvas id="sky"> when the page has one
   (the home page does); otherwise it adds <canvas id="sky" class="dw-sky"> as the first thing in <body>.
   Fixed star positions, a few that twinkle. It stops drawing while the tab is hidden or the canvas is scrolled
   out of view, and holds still when the visitor asks for reduced motion. window.DWTheme.sky() redraws it. */
(function () {
"use strict";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let raf = 0, inView = true, watching = false;

function sky() {
  let c = document.getElementById("sky");
  if (!c) { c = document.createElement("canvas"); c.id = "sky"; c.className = "dw-sky"; c.setAttribute("aria-hidden", "true"); document.body.prepend(c); }
  cancelAnimationFrame(raf);
  if (getComputedStyle(c).display === "none") return;
  const W = c.clientWidth, H = c.clientHeight, dpr = Math.min(2, devicePixelRatio || 1); c.width = W * dpr; c.height = H * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr);
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const glow = (x, y, r, col) => { const q = g.createRadialGradient(x, y, 0, x, y, r); q.addColorStop(0, col); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.fillRect(0, 0, W, H); };
  const stars = [], n = Math.round(W * H / 5200);
  for (let i = 0; i < n; i++) stars.push({ x: rnd() * W, y: rnd() * H, r: rnd() < 0.08 ? 1.3 : rnd() * 0.7 + 0.3, a: rnd() * 0.6 + 0.2, tw: rnd() < 0.12, ph: rnd() * 6.28 });
  const paint = t => { g.clearRect(0, 0, W, H);
    glow(W * 0.82, 120, Math.max(420, W * 0.45), "rgba(56,104,190,.20)"); glow(W * 0.12, 520, Math.max(360, W * 0.35), "rgba(96,70,170,.12)");
    for (const s of stars) { g.globalAlpha = s.tw ? s.a * (0.55 + 0.45 * Math.sin(t / 900 + s.ph)) : s.a; g.fillStyle = "#dfe8ff"; g.beginPath(); g.arc(s.x, s.y, s.r, 0, 6.3); g.fill(); } g.globalAlpha = 1; };
  paint(0);
  if (!watching && "IntersectionObserver" in window) { watching = true; new IntersectionObserver(e => { inView = e[e.length - 1].isIntersecting; }).observe(c); }
  if (!reduce) { let last = 0; const loop = t => { raf = requestAnimationFrame(loop); if (document.hidden || !inView || t - last < 80) return; last = t; paint(t); }; raf = requestAnimationFrame(loop); }
}

let rt, lastW = innerWidth;
addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; clearTimeout(rt); rt = setTimeout(sky, 150); });
window.DWTheme = { sky };
if (document.body) sky(); else addEventListener("DOMContentLoaded", sky);
})();

/* Opening touches: one small effect on some pages as they open, picked by Dawson (Nov 27 2026).
     Projects: a meteor skims the top of the Earth (on open, then every 30 s while the top of the page is on screen),
               and the cost map draws in from the costs across to the industries.
     About: San Diego's coordinates tune in under the heading each time the About view opens.
     Page not found: a small satellite drifts across the sky.
     Market Watch overview: the summary cards power on one after another and their figures count up.
     Market Watch industry pages: each cost's sparkline draws left to right and its latest point pops in.
     M5 Forecasting: the leaderboard place counts down from 5,582nd to 27th.
   Each one stays out of the way (nothing to click, no delay before the page can be used), ends with every word and number
   exactly as the page wrote it, uses theme colors only, and is skipped for visitors who ask for reduced motion.
   The styles they use are at the end of /theme.css. */
(function () {
"use strict";
if (matchMedia("(prefers-reduced-motion: reduce)").matches || !Element.prototype.animate) return;
const ease = "cubic-bezier(.22,.8,.24,1)";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
// wait for something the page draws after load (up to 15 s)
const wait = sel => new Promise(res => { const t0 = performance.now(); (function tick() { const e = document.querySelector(sel);
  if (e) return res(e); if (performance.now() - t0 > 15000) return res(null); requestAnimationFrame(tick); })(); });
// wait until an element is on screen
const seen = el => new Promise(res => { if (!("IntersectionObserver" in window)) return res();
  const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); res(); } }, { threshold: 0.1 }); io.observe(el); });
// count a figure up (or down) to the value shown, then put the page's own text back
function count(el, dur) {
  const orig = el.textContent, m = orig.match(/[-+−]?\d[\d,]*\.?\d*/); if (!m) return;
  const target = parseFloat(m[0].replace(/,/g, "").replace("−", "-")), dec = (m[0].split(".")[1] || "").length, comma = m[0].includes(",");
  const fmt = v => { let s = Math.abs(v).toFixed(dec); if (comma) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return (v < 0 ? (m[0][0] === "−" ? "−" : "-") : m[0][0] === "+" ? "+" : "") + s; };
  el.setAttribute("aria-label", orig); const t0 = performance.now();
  (function step(now) { const t = Math.min(1, (now - t0) / dur);
    el.textContent = orig.replace(m[0], fmt(target * (1 - Math.pow(1 - t, 3))));
    if (t < 1) requestAnimationFrame(step); else { el.textContent = orig; el.removeAttribute("aria-label"); } })(t0);
}

// Projects: the meteor
async function meteor(first) {
  const globe = document.getElementById("globe"); if (!globe) return;
  const gr = globe.getBoundingClientRect(); if (gr.bottom < 0) return;
  const c = document.createElement("canvas"); c.className = "dw-fx-over"; c.setAttribute("aria-hidden", "true"); document.body.append(c);
  const W = innerWidth, H = Math.min(760, innerHeight), dpr = Math.min(2, devicePixelRatio || 1);
  c.width = W * dpr; c.height = H * dpr; c.style.height = H + "px"; const g = c.getContext("2d"); g.scale(dpr, dpr);
  const r = first ? 0.5 : Math.random(), steel = css("--steel") || "#7cc7f2";
  const x0 = W * (0.12 + 0.22 * r), y0 = -10, x1 = gr.left + gr.width * (0.36 + 0.14 * r), y1 = gr.top + scrollY + gr.height * (0.03 + 0.06 * r);
  const ang = Math.atan2(y1 - y0, x1 - x0), dur = 1300, t0 = performance.now();
  await new Promise(res => { (function f(now) { const t = Math.min(1, (now - t0) / dur), e = t * t * (3 - 2 * t);
    g.clearRect(0, 0, W, H);
    const hx = x0 + (x1 - x0) * e, hy = y0 + (y1 - y0) * e;
    const life = t < 0.75 ? 1 : 1 - (t - 0.75) / 0.25, heat = 0.5 + 0.9 * Math.max(0, (t - 0.55) / 0.45), tail = 150 * life + 30;
    const tx = hx - Math.cos(ang) * tail, ty = hy - Math.sin(ang) * tail;
    const lg = g.createLinearGradient(tx, ty, hx, hy); lg.addColorStop(0, "rgba(223,232,255,0)"); lg.addColorStop(1, `rgba(223,232,255,${0.85 * life})`);
    g.strokeStyle = lg; g.lineWidth = 1.6; g.lineCap = "round"; g.beginPath(); g.moveTo(tx, ty); g.lineTo(hx, hy); g.stroke();
    const q = g.createRadialGradient(hx, hy, 0, hx, hy, 10 * heat); q.addColorStop(0, `rgba(255,255,255,${life})`); q.addColorStop(0.4, steel + "88"); q.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = q; g.fillRect(hx - 20, hy - 20, 40, 40);
    if (t < 1) requestAnimationFrame(f); else res(); })(t0); });
  c.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300 }).finished.then(() => c.remove());
}
const onProjects = () => document.documentElement.dataset.view !== "about";
async function projects() {
  await sleep(500);
  if (onProjects()) meteor(true);
  setInterval(() => { if (!document.hidden && scrollY < 500 && onProjects()) meteor(false); }, 30000);
  // the cost map draws in: dots top to bottom, lines from the costs across to the industries, then the industries in rank order
  const p = await wait("#stage svg path.lk"); if (!p) return;
  const svg = p.ownerSVGElement; await seen(svg);
  svg.querySelectorAll("circle.dn").forEach(d => d.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: +d.getAttribute("cy") * 0.9, fill: "backwards" }));
  svg.querySelectorAll("path.lk").forEach(l => { let L = 0; try { L = l.getTotalLength(); } catch (e) {} if (!L) return;
    const y = parseFloat((l.getAttribute("d") || "").split(/[ ,]/)[1]) || 0;
    l.animate([{ strokeDasharray: L + " " + L, strokeDashoffset: L }, { strokeDasharray: L + " " + L, strokeDashoffset: 0 }], { duration: 1000, delay: 250 + y * 0.9, easing: ease, fill: "backwards" }); });
  svg.querySelectorAll(".irow").forEach((row, i) => row.animate([{ opacity: 0, transform: "translateX(-6px)" }, { opacity: 1, transform: "none" }], { duration: 420, delay: 900 + i * 45, easing: ease, fill: "backwards" }));
}

// About: the coordinates tune in, each time the About view opens
function about() {
  const h = document.querySelector("#v-about h1"); if (!h) return;
  const s = document.createElement("div"); s.className = "dw-fx-coord"; s.setAttribute("aria-hidden", "true"); h.after(s);
  const goal = "32.7157° N   117.1611° W"; let run = 0;
  const tune = () => { const id = ++run, t0 = performance.now(); s.classList.remove("locked");
    (function f(now) { if (id !== run) return; const t = Math.min(1, (now - t0) / 1100), lock = Math.floor(goal.length * t);
      s.textContent = [...goal].map((ch, i) => i < lock || !/\d/.test(ch) ? ch : String(Math.floor(Math.random() * 10))).join("");
      if (t < 1) requestAnimationFrame(f); else { s.textContent = goal; s.classList.add("locked"); } })(t0); };
  s.textContent = goal; s.classList.add("locked");
  const isAbout = () => document.documentElement.dataset.view === "about";
  if (isAbout()) setTimeout(tune, 300);
  let was = isAbout();
  new MutationObserver(() => { const now = isAbout(); if (now && !was) setTimeout(tune, 300); was = now; })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-view"] });
}

// Page not found: a satellite drifts across the sky
function satellite() {
  const s = document.createElement("div"); s.className = "dw-fx-sat"; s.setAttribute("aria-hidden", "true");
  s.innerHTML = '<svg viewBox="0 0 44 20" width="44" height="20"><rect x="0" y="6" width="14" height="8" rx="1" fill="var(--ink-3)" stroke="var(--steel)" stroke-width=".8"/><path d="M3.5 6v8M7 6v8M10.5 6v8" stroke="var(--rule)" stroke-width=".7"/><rect x="30" y="6" width="14" height="8" rx="1" fill="var(--ink-3)" stroke="var(--steel)" stroke-width=".8"/><path d="M33.5 6v8M37 6v8M40.5 6v8" stroke="var(--rule)" stroke-width=".7"/><path d="M14 10h4M26 10h4" stroke="var(--pencil)" stroke-width=".8"/><rect x="18" y="5" width="8" height="10" rx="2" fill="var(--pencil)"/><circle class="blink" cx="22" cy="3" r="1.4" fill="var(--alert)"/></svg>';
  document.body.append(s);
  s.animate([{ transform: "translate(-60px, 230px) rotate(-8deg)" }, { transform: `translate(${innerWidth + 60}px, 90px) rotate(-14deg)` }], { duration: 38000, easing: "linear" }).finished.then(() => s.remove());
}

// Market Watch overview: the summary cards power on
async function powerOn() {
  if (!await wait(".kpis .card")) return;
  document.querySelectorAll(".kpis .card, .strip .kpi").forEach((c, i) => {
    const d = 120 + i * 110; c.classList.add("dw-fx-power"); c.style.setProperty("--dw-fx-d", d + "ms");
    c.animate([{ opacity: 0.15 }, { opacity: 1 }], { duration: 420, delay: d, fill: "backwards" });
    c.querySelectorAll(".n, .v").forEach(n => { if (/\d/.test(n.textContent)) setTimeout(() => count(n, 800), d); });
    setTimeout(() => c.classList.remove("dw-fx-power"), d + 1400);
  });
}

// Market Watch industry pages: the sparklines draw in
async function sparklines() {
  const first = await wait(".spark svg path"); if (!first) return;
  await seen(first.closest("table") || first);
  document.querySelectorAll(".spark svg").forEach((s, i) => {
    const p = s.querySelector("path"), c = s.querySelector("circle"), d = i * 70;
    let L = 0; try { L = p ? p.getTotalLength() : 0; } catch (e) {}
    if (L) p.animate([{ strokeDasharray: L + " " + L, strokeDashoffset: L }, { strokeDasharray: L + " " + L, strokeDashoffset: 0 }], { duration: 700, delay: d, easing: ease, fill: "backwards" });
    if (c) { c.style.transformBox = "fill-box"; c.style.transformOrigin = "center";
      c.animate([{ transform: "scale(0)", opacity: 0 }, { transform: "scale(1.8)", opacity: 1, offset: 0.6 }, { transform: "scale(1)", opacity: 1 }], { duration: 420, delay: d + 650, fill: "backwards" }); }
  });
}

// M5 Forecasting: the leaderboard place counts down to 27th
async function climb() {
  const v = [...document.querySelectorAll(".fig .v")].find(e => /^\d+(st|nd|rd|th) of 5,582/.test(e.textContent.trim())); if (!v) return;
  await sleep(300);
  const orig = v.textContent, top = parseInt(orig.replace(/^\D*/, ""), 10), t0 = performance.now();
  const ord = n => n.toLocaleString("en-US") + ({ 1: "st", 2: "nd", 3: "rd" }[(n % 100 > 10 && n % 100 < 14) ? 0 : n % 10] || "th");
  v.setAttribute("aria-label", orig); v.style.fontVariantNumeric = "tabular-nums";
  (function f(now) { const t = Math.min(1, (now - t0) / 1800), n = Math.round(5582 - (5582 - top) * (1 - Math.pow(1 - t, 4)));
    v.textContent = orig.replace(/^(\s*)\d+(st|nd|rd|th)/, "$1" + ord(n));
    if (t < 1) requestAnimationFrame(f); else { v.textContent = orig; v.removeAttribute("aria-label"); v.parentElement.classList.add("dw-fx-glint"); } })(t0);
}

function start() {
  const path = location.pathname.replace(/index\.html$/, "");
  if (document.querySelector("main.missing")) satellite();
  else if (document.getElementById("v-home")) { projects(); about(); }
  else if (/^\/market-watch\/$/.test(path)) powerOn();
  else if (/^\/market-watch\/[a-z0-9-]+\/$/.test(path)) sparklines();
  else if (/^\/m5-forecast\/$/.test(path)) climb();
}
if (document.readyState === "loading") addEventListener("DOMContentLoaded", start); else start();
})();
