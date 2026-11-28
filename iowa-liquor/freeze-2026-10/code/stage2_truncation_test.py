"""Stage 2 truncation test (judge's Addendum 8, before any score is read): forecasts for one origin made from the full
data must be identical to forecasts made after deleting every month after that origin. Runs the statistical members
(s2stat.run_origin) both ways, in-process, and compares every series, horizon and member (mean and 7 quantiles).
Static attributes (the series map, links, category) are the same in both runs by construction.
Usage: python truncation_test.py <base> <origin YYYY-MM>   ->  stage2/truncation_test_<origin>.csv"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import s2stat
from s2common import Data, progress

QC = s2stat.QC
if __name__ == "__main__":
    base, origin = Path(sys.argv[1]), sys.argv[2]
    res = {}
    for label, asof in (("full", None), ("truncated", origin)):
        t0 = time.time()
        d = Data(base, asof=asof); s2stat.D = d
        progress(base, f"truncation test {origin}: {label} data loaded ({d.S:,} series, last month {d.months[-1]})")
        df, log = s2stat.run_origin(d.mi[pd.Period(origin, freq="M")])
        df["series_id"] = d.sids[df.sid]
        res[label] = df.drop(columns="sid").set_index(["series_id", "h", "member"]).sort_index()
        progress(base, f"truncation test {origin}: {label} run done in {time.time() - t0:.0f}s")
    a, b = res["full"], res["truncated"]
    j = a.join(b, how="outer", lsuffix="_full", rsuffix="_trunc")
    cols = ["mean"] + QC
    diff = np.nanmax(np.abs(np.stack([j[c + "_full"].to_numpy(float) - j[c + "_trunc"].to_numpy(float) for c in cols], 1)), axis=1)
    j["max_abs_diff"] = diff
    only = j[[c + "_full" for c in cols]].isna().all(1) | j[[c + "_trunc" for c in cols]].isna().all(1)
    j["missing_on_one_side"] = only
    j.reset_index().to_csv(base / "stage2" / f"truncation_test_{origin}.csv", index=False)
    same_class = (j.pool_class_full == j.pool_class_trunc).all()
    bad = j[(j.max_abs_diff > 1e-9) | only]
    print(f"truncation test {origin}: rows full {len(a):,}, truncated {len(b):,}; rows on one side only {int(only.sum())}; "
          f"rows differing by > 1e-9: {int((j.max_abs_diff > 1e-9).sum())}; max abs diff {np.nanmax(diff):.3g}; "
          f"classes identical {bool(same_class)} -> {'IDENTICAL' if len(bad) == 0 and same_class else 'DIFFERENT'}")
