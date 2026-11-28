"""Stage 2 truncation test for the tree model (judge's Addendum 8): the fit through Dec of the year before the origin
and its forecasts for that origin must be identical whether or not the months after the origin exist. Fits the three
quantiles of the tuning proxy per horizon with fixed rounds (from the last timing trial), both ways, and compares.
Usage: python truncation_test_tree.py <base> <origin YYYY-MM>   ->  stage2/truncation_test_tree_<origin>.csv"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import s2tree
from s2common import Data, progress

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    base, origin = Path(sys.argv[1]), sys.argv[2]
    threads = max(1, (os.cpu_count() or 2) - 2)
    tr = pd.read_csv(base / "stage2" / "tree" / "trials.csv").iloc[-1]
    rounds = {(int(k.split("_")[0][1:]), k.split("_", 1)[1]): v for k, v in json.loads(tr.rounds).items()}
    op = pd.Period(origin, freq="M"); fy = op.year - 1
    res = {}
    for label, asof in (("full", None), ("truncated", origin)):
        d = Data(base, asof=asof)
        cutoff = d.mi[pd.Period(f"{fy}-12", "M")]
        models, feats, sc, cats, _ = s2tree.fit_models(d, cutoff, dict(s2tree.START), "base", threads, s2tree.Q3, rounds=rounds)
        p = s2tree.predict(d, models, feats, sc, cats, [d.mi[op]], "base")
        p["series_id"] = d.sids[p.sid]
        res[label] = p.drop(columns=["sid"]).set_index(["series_id", "o", "h"]).sort_index()
        progress(base, f"tree truncation test {origin}: {label} done ({len(p):,} rows)")
    j = res["full"].join(res["truncated"], how="outer", lsuffix="_full", rsuffix="_trunc")
    cols = s2tree.QC3
    diff = np.nanmax(np.abs(np.stack([j[c + "_full"] - j[c + "_trunc"] for c in cols], 1)), axis=1)
    j["max_abs_diff"] = diff
    j.reset_index().to_csv(base / "stage2" / f"truncation_test_tree_{origin}.csv", index=False)
    one = int(j[[c + "_full" for c in cols]].isna().all(1).sum() + j[[c + "_trunc" for c in cols]].isna().all(1).sum())
    n_diff = int((diff > 1e-9).sum())
    print(f"tree truncation test {origin}: rows full {len(res['full']):,}, truncated {len(res['truncated']):,}; one side only {one}; "
          f"differing > 1e-9: {n_diff}; max abs diff {np.nanmax(diff):.3g} -> {'IDENTICAL' if one == 0 and n_diff == 0 else 'DIFFERENT'}")
