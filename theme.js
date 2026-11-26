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
