"""Watch list (ruling-01e-amend item 9): own 2023-24 scaled pinball of 84222 and 84226 per layer and year, with and
without the unit_change_window months. 2023-24 targets only. Usage: python watch_list.py <base> -> stage2/watch_list_scores.csv"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q, pinball

QC = [f"q{int(round(q * 100)):02d}" for q in Q]
base = Path(sys.argv[1]); d = Data(base)
L = pd.read_parquet(base / "stage2" / "layers.parquet")
rows = []
for it in ("84222", "84226"):
    s = int(np.flatnonzero(d.sids == it)[0])
    g = L[L.sid == s]
    for r in g.itertuples():
        t = r.o + r.h
        if t >= d.M or d.months[t].year not in (2023, 2024) or np.isnan(d.Y[s, t]):
            continue
        sc = d.scale(r.o)[s]
        loss = pinball(np.array([d.Y[s, t]]), np.array([[getattr(r, c) for c in QC]]))[0] / (sc if sc > 0 else 1)
        rows.append(dict(series_id=it, layer=r.layer, year=d.months[t].year, window=bool(d.window[s, t]), loss=loss))
R = pd.DataFrame(rows)
out = R.groupby(["series_id", "layer", "year"]).apply(lambda g: pd.Series(dict(
    all_months=g.loss.mean(), excl_window=g.loss[~g.window].mean(), n_all=len(g), n_excl=int((~g.window).sum()))),
    include_groups=False).reset_index()
out.to_csv(base / "stage2" / "watch_list_scores.csv", index=False)
print(f"watch list: {len(out)} rows")
