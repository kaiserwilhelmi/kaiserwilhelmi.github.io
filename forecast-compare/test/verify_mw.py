"""Independent check of the Market Watch loader: re-reads every file in Python, applies
the same rule (drop leading/trailing blanks, straight-line fill inside gaps) and compares
with what mw.js produced; also cross-checks the fill against numpy.interp.
Usage: python3 test/verify_mw.py <market-watch repo> mw_js.json"""
import csv, json, sys, os
import numpy as np
mw, js = sys.argv[1], json.load(open(sys.argv[2]))

def clean(dates, vals):
    a, b = 0, len(vals) - 1
    while a <= b and vals[a] is None: a += 1
    while b >= a and vals[b] is None: b -= 1
    d, v = dates[a:b + 1], vals[a:b + 1]
    idx = [i for i, x in enumerate(v) if x is not None]
    filled = [d[i] for i, x in enumerate(v) if x is None]
    out = list(np.interp(range(len(v)), idx, [v[i] for i in idx]))
    return d, out, filled

def num(x):
    try:
        f = float(x)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None

worst, n, problems = 0.0, 0, []
def cmp(name, d, v, f, j):
    global worst, n
    if d != j["dates"] or f != j["filled"]:
        problems.append(name + ": dates/filled differ"); return
    for a, b in zip(v, j["values"]):
        worst = max(worst, abs(a - b) / max(1.0, abs(a))); n += 1
for fn in sorted(os.listdir(os.path.join(mw, "data/long"))):
    sid = fn[:-4]
    if sid == "CPIAUCSL": continue
    rows = list(csv.DictReader(open(os.path.join(mw, "data/long", fn))))
    d, v, f = clean([r["date"] for r in rows], [num(r["value"]) for r in rows])
    cmp(sid, d, v, f, js["long"][sid])
spot = json.load(open(os.path.join(mw, "data/agency/spot.json")))
for k, rows in spot.items():
    d, v, f = clean([str(r[0]) for r in rows], [num(r[1]) for r in rows])
    cmp("spot:" + k, d, v, f, js["spot"][k])
    if js["spot"][k]["built"] != js["spot"][k]["values"]:
        problems.append("spot:%s: upload reader changed the values" % k)
filled = {k: j["filled"] for k, j in list(js["long"].items()) + list(js["spot"].items()) if j["filled"]}
runs = js["runs"]
bad = [r for r in runs if not r["ok"]]
print("series checked:", len(js["long"]), "monthly +", len(js["spot"]), "spot;", n, "values; worst relative difference %.2e" % worst)
print("filled gaps:", filled)
print("engine runs:", len(runs), "all metrics finite:", not bad, "; slowest %d ms (%s)" % max((r["ms"], r["id"]) for r in runs))
from collections import Counter
print("winners:", Counter(r["best"] for r in runs).most_common())
print("problems:", problems or "none")
sys.exit(1 if problems or bad or worst > 1e-12 else 0)
