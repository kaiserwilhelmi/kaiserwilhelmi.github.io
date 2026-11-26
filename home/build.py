"""Build the site's two pages, ../index.html (Projects) and ../about/index.html (About), from template.html.

They are one page with two views. A click on About or Projects switches the view in place (see space.src.js),
so nothing reloads. about/index.html is the same page opened on the About view, with its own title and address,
for people who land on /about/ directly. Edit the About text in template.html, inside <div id="v-about">.

The page carries a copy of the numbers it shows so it is complete on first paint:
  - Market Watch: home_summary.summary() of analytics.json, from a clone of kaiserwilhelmi/market-watch
    (MW_REPO, default ../../market-watch; MW_DATA_DIR if the data sits elsewhere, e.g. its data branch).
    The live page then replaces this copy with /market-watch/data/home.json.
  - Supplier Scorecard: scored with score.py from a clone of kaiserwilhelmi/supplier-scorecard
    (SC_REPO, default ../../supplier-scorecard), for the last 3, 6 and 12 months.
  - Forecast preview: fc.json, written by `node prep_fc.js` from the Forecast tool's own engine.

It also writes ../space.js (Earth graphic, shared with the About page; the stars come from /theme.js) from space.src.js plus
land.json, a land/sea grid written by `node prep_globe.js` from Natural Earth (public domain). The grid only
needs rebuilding if the grid itself should change.

Run: node prep_fc.js && python build.py
"""
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MW = Path(os.environ.get("MW_REPO") or HERE / ".." / ".." / "market-watch").resolve()
SC = Path(os.environ.get("SC_REPO") or HERE / ".." / ".." / "supplier-scorecard").resolve()
MW_DATA = Path(os.environ.get("MW_DATA_DIR") or MW / "data")
sys.path[:0] = [str(MW), str(SC)]
from home_summary import summary   # noqa: E402  (market-watch)
import score as S                  # noqa: E402  (supplier-scorecard)

D = summary(json.loads((MW_DATA / "analytics.json").read_text()))

rows = list(csv.DictReader(open(SC / "data" / "supplier_monthly.csv", encoding="utf-8-sig")))
months = sorted({r["month"] for r in rows})
D["sc"] = {}
for n in (3, 6, 12):
    use, by = months[-n:], {}
    for r in rows:
        if r["month"] in use:
            by.setdefault(r["supplier"], []).append(r)
    out = []
    for sup, rs in by.items():
        m = S.metrics(rs)
        sc = S.score(m)
        out.append({"n": sup, "c": rs[0]["category"], "spend": round(m["spend"]), "score": round(sc, 1), "tier": S.tier(sc),
                    "k": {k: [round(m[k], 2), round(S.kpi_points(m[k], S.KPIS[k][2], S.KPIS[k][3]))] for k in S.KPIS if k in m}})
    D["sc"][n] = {"from": use[0], "to": use[-1], "rows": sorted(out, key=lambda z: -z["score"])}
D["kpis"] = {k: list(v) for k, v in S.KPIS.items()}
D["fc"] = json.loads((HERE / "fc.json").read_text())

blob = json.dumps(D, separators=(",", ":")).replace("</", "<\\/")
page = (HERE / "template.html").read_text()
assert page.count("/*__DATA__*/null") == 1
page = page.replace("/*__DATA__*/null", blob)

# Browsers keep each file for a few minutes. Stamp the shared scripts, the theme and the font list with a short hash of their
# contents, so a page never runs with an older copy of either one after an update.
import hashlib   # noqa: E402
space = (HERE / "space.src.js").read_text()
assert space.count("/*__LAND__*/null") == 1
space = space.replace("/*__LAND__*/null", (HERE / "land.json").read_text().strip())
(HERE.parent / "space.js").write_text(space)
for ref, text in (("/space.js", space), ("/fonts/fonts.css", (HERE.parent / "fonts" / "fonts.css").read_text()),
                  ("/theme.css", (HERE.parent / "theme.css").read_text()), ("/theme.js", (HERE.parent / "theme.js").read_text())):
    assert page.count(f'"{ref}"') == 1, ref
    page = page.replace(f'"{ref}"', f'"{ref}?v={hashlib.sha256(text.encode()).hexdigest()[:10]}"')
(HERE.parent / "index.html").write_text(page)

# the same page, opened on the About view
ABOUT_DESC = "About Dawson Wilhelmi: controller and supply chain student focused on procurement analytics."
HOME_DESC = ("Procurement and supply chain analytics projects by Dawson Wilhelmi: forecast method comparison, "
             "industry input-cost tracking and supplier scorecard.")
swaps = [('<html lang="en" data-view="hero">', '<html lang="en" data-view="about">', 1),
         ("<title>Dawson Wilhelmi · Projects</title>", "<title>Dawson Wilhelmi · About</title>", 1),
         ('<meta property="og:title" content="Dawson Wilhelmi · Projects">', '<meta property="og:title" content="Dawson Wilhelmi · About">', 1),
         (f'content="{HOME_DESC}"', f'content="{ABOUT_DESC}"', 2),
         ('<meta property="og:url" content="https://dawsonwilhelmi.com/">', '<meta property="og:url" content="https://dawsonwilhelmi.com/about/">', 1),
         ('<link rel="canonical" href="https://dawsonwilhelmi.com/">', '<link rel="canonical" href="https://dawsonwilhelmi.com/about/">', 1)]
about = page
for old, new, n in swaps:
    assert about.count(old) == n, old
    about = about.replace(old, new)
(HERE.parent / "about" / "index.html").write_text(about)
print(f"index.html and about/index.html written ({len(page):,} bytes each; Market Watch data built {D['built']}, "
      f"{len(D['series'])} series, {len(D['ind'])} industries)")
