"""Ruling-04 items 4 and 6, written to the freeze outputs. No model choice is made here.
- coverage_note_data.csv (item 6): for the chosen layer, per year (2025 = judging year, 2026 = report only):
  pooled 90% and 50% coverage; by class the coverage, the share below the 5% line and above the 95% line, and the
  class's dollar share; and the dollar-weighted share of series-months where the median was above the actual.
  Same masks and weights as s2eval.coverage (active at the origin, actual observed, no open handover; trailing-12
  dollar weights normalised per origin and horizon, then averaged).
- forecast_live_challenger_d.csv (item 4): layer d at the live origin, same units and dollars as the published file,
  labelled "challenger, not the published forecast".
Usage: python s2freeze_extras.py <base>"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q

warnings.filterwarnings("ignore")
QC = [f"q{int(round(q * 100)):02d}" for q in Q]
base = Path(sys.argv[1]); out = base / "stage2"
d = Data(base)
chosen = json.load(open(out / "chosen_layer.json"))["chosen_layer"]
L = pd.read_parquet(out / "layers.parquet")

rows = []
for year in (2025, 2026):
    g0 = L[L.layer == chosen]
    t = (g0.o + g0.h).to_numpy()
    g0 = g0[[(k < d.M) and d.months[k].year == year for k in t]]
    for (o, h), g in g0.groupby(["o", "h"]):
        s = g.sid.to_numpy(); y = d.Y[s, o + h]
        ok = ~np.isnan(y) & d.active(o)[s] & ~d.open_handover(o)[s]
        w = d.weight12(o)[s]
        for cl in ["all", "regular", "intermittent", "new"]:
            m = ok & ((g.pool_class.to_numpy() == cl) if cl != "all" else True)
            if not m.any() or w[m].sum() == 0:
                continue
            ww = w[m] / w[m].sum(); yy = y[m]
            rows.append(dict(year=year, o=o, h=h, cls=cl,
                             in90=(ww * ((yy >= g.q05.to_numpy()[m]) & (yy <= g.q95.to_numpy()[m]))).sum(),
                             in50=(ww * ((yy >= g.q25.to_numpy()[m]) & (yy <= g.q75.to_numpy()[m]))).sum(),
                             below05=(ww * (yy < g.q05.to_numpy()[m])).sum(), above95=(ww * (yy > g.q95.to_numpy()[m])).sum(),
                             median_above_actual=(ww * (g.q50.to_numpy()[m] > yy)).sum(),
                             median_equal_actual=(ww * (g.q50.to_numpy()[m] == yy)).sum(),
                             dollar_share=w[m].sum() / w[ok].sum()))
R = pd.DataFrame(rows)
note = R.groupby(["year", "cls"])[["in90", "in50", "below05", "above95", "median_above_actual", "median_equal_actual",
                                   "dollar_share"]].mean().reset_index()
note.insert(0, "layer", chosen)
note["status"] = np.where(note.year == 2025, "judging year (section 5)", "report only (ruling-04 item 2)")
note.to_csv(out / "coverage_note_data.csv", index=False)
print("coverage note data (%):"); print((note.set_index(["year", "cls"])[["in90", "in50", "below05", "above95",
      "median_above_actual", "dollar_share"]] * 100).round(1).to_string())

# challenger: layer d at the live origin
o = d.M - 1
pub = pd.read_csv(out / "forecast_live.csv", dtype={"series_id": str})
D = L[(L.layer == "d") & (L.o == o)].copy()
D["series_id"] = d.sids[D.sid.to_numpy()]
D = D.rename(columns={"mean": "units_mean", **{c: f"units_{c}" for c in QC}})
keep = ["series_id", "description", "unit", "category", "pool_class", "origin", "target_month", "h", "price_per_unit"]
C = pub[keep].merge(D[["series_id", "h", "units_mean", *[f"units_{c}" for c in QC]]], on=["series_id", "h"], how="left")
C["dollars_mean"] = C.units_mean * C.price_per_unit
C["label"] = "challenger, not the published forecast (layer d: layer c with conformal calibration; ruling-04 item 4)"
C.to_csv(out / "forecast_live_challenger_d.csv", index=False)
print(f"challenger d: {C.series_id.nunique():,} series, {int(C.units_mean.isna().sum())} rows without a layer d value")
