"""June diagnostic (ruling-01d-amend item 2): fitted June seasonal index of each 99 mini with a May 2023 restated
break, beside its category's. Report only, not a choice. Fit: additive-error, additive-season ETS (no trend, period 12)
on per-order-day values through 2024-12 (no 2025 or 2026 target is touched): items on restated bottles, categories on
dollars (units are never summed above the product, decision 52). Index = 1 + (fitted June seasonal state in 2024) /
(mean fitted level over 2024). Writes stage2/june_diagnostic.csv. Usage: python june_diag.py <base>"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

warnings.filterwarnings("ignore")
base = Path(sys.argv[1]); d = Data(base)
o = d.mi[pd.Period("2024-12", "M")]; eff = d.eff_days(o)[:o + 1]
ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str})
isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
x = ap[(ap.month.astype(str).str[:7] == "2023-05") & (ap.outcome == "restated")]
sids = sorted({isr.get(i, i) for i in x.item_no})
pos = {s: i for i, s in enumerate(d.sids)}


def june_index(y):
    y = pd.Series(np.nan_to_num(y))
    r = ETSModel(y, error="add", trend=None, seasonal="add", seasonal_periods=12).fit(disp=False)
    lev, sea = np.asarray(r.level), np.asarray(r.season)
    k = len(y) - 7          # index of 2024-06 when y ends at 2024-12
    s12 = sea[-12:]         # statsmodels pins one initial state at 0 instead of centring; centre over the last 12 months
    return 1 + (sea[k] - s12.mean()) / lev[-12:].mean()


rows = []
cat_cache = {}
for s in sids:
    i = pos[s]; c = d.category[i]
    y = d.Y[i, d.first[i]:o + 1] / eff[d.first[i]:]
    if c not in cat_cache:
        idx = np.flatnonzero(d.category == c)
        cd = np.nansum(d.D[idx, :o + 1], axis=0); f = int(np.argmax(cd > 0))
        cat_cache[c] = june_index(cd[f:] / eff[f:])
    rows.append(dict(series_id=s, category=c, months_history=len(y), item_june_index=june_index(y),
                     category_june_index=cat_cache[c]))
r = pd.DataFrame(rows); r["ratio"] = r.item_june_index / r.category_june_index
r.to_csv(base / "stage2" / "june_diagnostic.csv", index=False)
print(f"june diagnostic: {len(r)} items; item index median {r.item_june_index.median():.3f}, category {r.category_june_index.median():.3f}")
