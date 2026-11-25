/* Upload regression test. Loads every file in test/uploads into the built page (headless
 * Chromium), reads it with FCUpload exactly as the page does, and checks the result against
 * test/expected_uploads.json: count, first and last date, first and last value, time unit,
 * filled periods, and the notes, warnings or error the page shows. Then checks the page itself
 * renders with no script errors, a finite MASE for the #1 method, a finite error vs naive and an 80% forecast
 * range (or "n/a" with the reason shown) once the background fitting is done. Exit code 1 on any mismatch.
 * Run after `python3 build.py`:  node test/test_uploads.js   (--write saves new expectations;
 * FC_PAGE=path/to/index.html tests another build, e.g. the live page before a fix) */
const { chromium } = require("playwright"); const fs = require("fs"), path = require("path");
const page = path.resolve(process.env.FC_PAGE || path.resolve(__dirname, "../index.html")), dir = path.resolve(__dirname, "uploads");
const expFile = path.resolve(__dirname, "expected_uploads.json"), write = process.argv.includes("--write");
const expected = fs.existsSync(expFile) ? JSON.parse(fs.readFileSync(expFile, "utf8")) : {};
(async () => {
  const b = await chromium.launch(), got = {}; let fails = 0;
  for (const f of fs.readdirSync(dir).sort()) {
    const p = await b.newPage(), errs = []; p.on("pageerror", e => errs.push(e.message));
    await p.goto("file://" + page); await p.waitForTimeout(300);
    const bytes = [...fs.readFileSync(path.join(dir, f))];
    const r = await p.evaluate(async ({ bytes, f }) => {
      try {
        const res = await window.FCUpload.read(new Uint8Array(bytes).buffer, f);
        const v = res.values, r6 = x => Math.round(x * 1e6) / 1e6;
        return { n: v.length, first: res.dates[0], last: res.dates[v.length - 1], v0: r6(v[0]), vLast: r6(v[v.length - 1]), unit: res.unit, values: v.map(r6),
          filled: (res.filledIdx || []).map(i => res.dates[i]), notes: res.notes, warnings: res.warnings };
      } catch (e) { return { error: e.message }; }
    }, { bytes, f });
    await p.setInputFiles("#file", path.join(dir, f)); await p.waitForTimeout(400);
    await p.waitForFunction(() => document.getElementById("busy").hidden, null, { timeout: 120000 }); await p.waitForTimeout(200);
    // the forecast range is built in a second stage; wait until it shows or the page says why not
    await p.waitForFunction(() => !document.getElementById("err").hidden || document.querySelector("#ranges table") || /history|could not|cannot/.test(document.getElementById("ranges").textContent), null, { timeout: 120000 }).catch(() => {});
    r.page = await p.evaluate(() => {
      const err = document.getElementById("err"), k = document.getElementById("kpis").innerText;
      const cell = document.querySelector("#tbl tbody tr td[data-m]"), rel = (/(?:Error|pool) vs naive\s*\n?\s*([^\n|]+)/.exec(k) || [])[1];
      const rng = (/80% range[^\n]*\n\s*([^\n]+)/.exec(k) || [])[1];
      return { err: err.hidden ? "" : err.innerText, mase: cell ? cell.textContent.replace("★", "").trim() : null, rel: rel ? rel.trim() : null,
        range: rng ? rng.trim() : null, fit: document.documentElement.getAttribute("data-fit") };
    });
    r.pageErrors = errs; got[f] = Object.assign({}, r, { values: undefined }); await p.close();
    if (write) continue;
    const e = expected[f], bad = [];
    if (!e) bad.push("no expectation recorded");
    else {
      for (const key of ["n", "first", "last", "v0", "vLast", "unit", "error"]) if (e[key] !== undefined && e[key] !== r[key]) bad.push(`${key}: expected ${JSON.stringify(e[key])}, got ${JSON.stringify(r[key])}`);
      if (e.filled && JSON.stringify(e.filled) !== JSON.stringify(r.filled)) bad.push(`filled: expected ${JSON.stringify(e.filled)}, got ${JSON.stringify(r.filled)}`);
      for (const i in e.at || {}) if (!r.values || r.values[i] !== e.at[i]) bad.push(`value ${+i + 1}: expected ${e.at[i]}, got ${r.values && r.values[i]}`);
      for (const s of e.noteHas || []) if (!(r.notes || []).some(x => x.includes(s))) bad.push(`missing note "${s}"`);
      for (const s of e.warnHas || []) if (!(r.warnings || []).some(x => x.includes(s))) bad.push(`missing warning "${s}"`);
      if (!e.error && r.page.err) bad.push(`page error: ${r.page.err}`);
      if (!e.error && !(r.page.mase && /^[\d.,]+$/.test(r.page.mase))) bad.push(`#1 average miss not finite on page: ${r.page.mase}`);
      if (!e.error && !(r.page.rel && /^[−+]?[\d.,]+%$/.test(r.page.rel))) bad.push(`error vs naive not finite on page: ${r.page.rel}`);
      if (!e.error && !(r.page.range && /^(?:[−-]?[\d.,]+ to [−-]?[\d.,]+|n\/a)$/.test(r.page.range))) bad.push(`80% range not shown on page: ${r.page.range}`);
    }
    if (errs.length) bad.push("script errors: " + errs.join("; "));
    console.log((bad.length ? "FAIL " : "ok   ") + f.padEnd(28) + (r.error ? "error: " + r.error.slice(0, 60) : `n=${r.n} ${r.first} to ${r.last} ${r.unit}`) + (r.page.range ? `  range ${r.page.range} (${r.page.fit})` : ""));
    bad.forEach(x => console.log("       " + x)); fails += bad.length ? 1 : 0;
  }
  await b.close();
  if (write) { fs.writeFileSync(path.resolve(__dirname, "uploads_actual.json"), JSON.stringify(got, null, 1)); console.log("wrote test/uploads_actual.json; review it, then copy the checked fields into expected_uploads.json"); return; }
  console.log(fails ? `${fails} file(s) failed` : `all ${Object.keys(got).length} files passed`); process.exit(fails ? 1 : 0);
})();
