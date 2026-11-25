"""Build the home page (../index.html) from template.html.

The page carries a copy of the numbers it shows so it is complete on first paint:
  - Market Watch: home_summary.summary() of analytics.json, from a clone of kaiserwilhelmi/market-watch
    (MW_REPO, default ../../market-watch; MW_DATA_DIR if the data sits elsewhere, e.g. its data branch).
    The live page then replaces this copy with /market-watch/data/home.json.
  - Supplier Scorecard: scored with score.py from a clone of kaiserwilhelmi/supplier-scorecard
    (SC_REPO, default ../../supplier-scorecard), for the last 3, 6 and 12 months.
  - Forecast preview: fc.json, written by `node prep_fc.js` from the Forecast tool's own engine.
  - Earth graphic: land.json, a land/sea grid written by `node prep_globe.js` from Natural Earth (public domain).
    It only needs rebuilding if the grid itself should change.

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
D["land"] = json.loads((HERE / "land.json").read_text())

blob = json.dumps(D, separators=(",", ":")).replace("</", "<\\/")
page = (HERE / "template.html").read_text()
assert page.count("/*__DATA__*/null") == 1
(HERE.parent / "index.html").write_text(page.replace("/*__DATA__*/null", blob))
print(f"index.html written ({len(page) + len(blob):,} bytes; Market Watch data built {D['built']}, "
      f"{len(D['series'])} series, {len(D['ind'])} industries)")
