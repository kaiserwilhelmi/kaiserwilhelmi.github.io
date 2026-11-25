"""Tolerance test against statsmodels (audit item J22): the engine's least-squares fits of simple exponential
smoothing, Holt and damped trend should reach at least the fit statsmodels finds (in-sample one-step SSE, ratio
<= 1.01) with the same bounds. Uses verify.py's fits, which match engine.js to 1e-9 (see verify.py).
Usage: python3 test/test_statsmodels.py [market-watch dir]   (no argument: the series in data/)"""
import csv, glob, os, sys, warnings
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verify as V
from statsmodels.tsa.holtwinters import ExponentialSmoothing
warnings.filterwarnings("ignore")

def series():
    if len(sys.argv) > 1:
        for f in sorted(glob.glob(os.path.join(sys.argv[1], "data/long/*.csv"))):
            v = [float(r["value"]) for r in csv.DictReader(open(f)) if r.get("value") not in (None, "", ".")]
            if len(v) > 40 and "CPIAUCSL" not in f: yield os.path.basename(f)[:-4], v
    else:
        for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "data", "*.csv"))): yield os.path.basename(f)[:-4], V.load(f)

B = (1e-4, 0.9999)
def sm_sse(y, kind):
    y = np.asarray(y, float)
    if kind == "ses": m = ExponentialSmoothing(y, initialization_method="estimated", bounds={"smoothing_level": B})
    elif kind == "holt": m = ExponentialSmoothing(y, trend="add", initialization_method="estimated", bounds={"smoothing_level": B, "smoothing_trend": B})
    else: m = ExponentialSmoothing(y, trend="add", damped_trend=True, initialization_method="estimated",
                                   bounds={"smoothing_level": B, "smoothing_trend": B, "damping_trend": (0.8, 0.98)})
    return float(m.fit().sse)

fails, rows = 0, []
for name, y in series():
    for kind, fn in (("ses", V.ses), ("holt", V.holt), ("damped", V.damped)):
        ours = fn(y, 1, 12)[1]["_sse"]; sm = sm_sse(y, kind); r = ours / sm
        rows.append(r); bad = r > 1.01; fails += bad
        print(f"{'FAIL' if bad else 'ok  '} {name:22s} {kind:7s} SSE ratio engine/statsmodels {r:.4f}")
print(f"{len(rows)} fits: median ratio {np.median(rows):.4f}, worst {max(rows):.4f}" + (f", {fails} above 1.01" if fails else ", all within 1.01"))
sys.exit(1 if fails else 0)
