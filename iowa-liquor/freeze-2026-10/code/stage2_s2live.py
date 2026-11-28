"""Live forecast files (protocol 1.10 sections 1, 2 and 7): the chosen layer at the last complete month, horizons 1-3.
Expected Iowa store orders (depletions).
- Product rows (forecast_live.csv): units as the state counts them, with the unit named (decision 52), mean + 7
  quantiles; liters from the decision 51 tier (proven: units x ml x factor; standard: units x ml; unknown: blank);
  dollars = units x the average price stores paid per unit (median of monthly dollars / restated units over the last 3
  months with orders, as of the origin). Flags for items ruled "flag, do not change" (ruling 01b items 5 and 6).
- Brand, category and state rows (forecast_live_levels.csv): bottom-up sums of product means. Dollars first, then
  covered liters with the share of dollars the liters cover; liters labelled partial when unknown-tier series carry over
  5% of the level's dollars. Units are never summed above the product. Brand totals carry the hand-checked share
  (decision 49).
- grading_rules.json: the live grading rules for breaks after the freeze (ruling 01b amendment item 7).
Usage: python s2live.py <base>"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import sys, json
from pathlib import Path
import numpy as np, pandas as pd, duckdb
sys.path.insert(0, str(Path(__file__).parent))
from s2common import Data, Q
from s2tree import price_asof

QC = [f"q{int(round(q * 100)):02d}" for q in Q]
FLAGS = {"28081": "pack 8 -> 12 in Aug 2026 with price halved: possible unit change, not provable; scored separately (ruling 01b)",
         "87035": "price toggles $21.00 / $4.95 by month: possibly two products on one number (ruling 01b item 5)",
         "65933": "item number reused for a 1.75 L bottle in Jun 2026 (ruling 01b item 5)",
         "84172": "unit flip in Jul-Aug 2012 with no pack evidence, left as recorded (ruling 01b item 5)",
         "84160": "unit flip in Jul-Aug 2012 and pack 10 -> 1 in Mar 2021 after an 8-year gap, left as recorded (ruling 01b item 5)"}

def unit_name(ml, factor, source):
    if factor == 1 or not source:
        return f"bottle of {ml:g} ml"
    if "unit break" in source:
        n = factor
        return f"pack of {n:g} x {ml:g} ml" if "size history" not in source else f"pack totalling {ml * factor:g} ml (recorded as {ml:g} ml)"
    return f"unit of {ml * factor:g} ml (recorded as {ml:g} ml)"

if __name__ == "__main__":
    base = Path(sys.argv[1]); out = base / "stage2"
    d = Data(base)
    chosen = json.load(open(out / "chosen_layer.json"))["chosen_layer"]
    L = pd.read_parquet(out / "layers.parquet")
    o = d.M - 1
    f = L[(L.layer == chosen) & (L.o == o)].copy()
    con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
    ser = con.execute('''
        SELECT s.series_id, ANY_VALUE(r.d) AS description, ANY_VALUE(r.ml) AS bottle_ml,
               string_agg(s.item_no, ' > ' ORDER BY s.first_order) AS item_numbers, COUNT(*) AS n_item_numbers
        FROM item_series s JOIN item_series r ON r.item_no = s.series_id GROUP BY 1''').df()
    # current unit of each series: recorded size of its latest month with orders and the line factor of that item / size
    cur = con.execute('''WITH l AS (SELECT i.series_id, s.item_no, s.bottle_volume_ml AS ml, s.sales_bottles AS b,
                                           date_trunc('month', s.order_date) AS m
                                    FROM sales s JOIN item_series i USING (item_no) WHERE s.sales_bottles > 0),
                         lm AS (SELECT series_id, MAX(m) AS m FROM l GROUP BY 1),
                         g AS (SELECT l.series_id, l.item_no, l.ml, SUM(l.b) AS b FROM l JOIN lm USING (series_id, m) GROUP BY 1, 2, 3),
                         r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY b DESC, item_no, ml) AS k FROM g)
                         SELECT series_id, item_no AS cur_item, ml AS cur_ml FROM r WHERE k = 1''').df()
    con.close()
    lf = pd.read_parquet(out / "units_lines_factor.parquet")
    tiers = pd.read_csv(out / "units_series_t12.csv", dtype={"series_id": str})[["series_id", "tier"]]
    bm = pd.read_csv(out / "brand_map.csv", dtype={"series_id": str})[["series_id", "brand", "brand_source"]]
    cur = cur.merge(lf[["item_no", "ml", "factor", "source"]].rename(columns={"item_no": "cur_item", "ml": "cur_ml"}),
                    on=["cur_item", "cur_ml"], how="left").fillna({"factor": 1.0, "source": ""})
    price = price_asof(d, o)
    f["series_id"] = d.sids[f.sid]
    f["origin"] = str(d.months[o]); f["target_month"] = [str(d.months[0] + (o + h)) for h in f.h]
    f["vendor_as_of_origin"] = d.vendor_by_month[f.sid, o]
    f["category"] = d.category[f.sid]
    f = f.merge(ser, on="series_id", how="left").merge(cur, on="series_id", how="left").merge(tiers, on="series_id", how="left") \
         .merge(bm, on="series_id", how="left")
    f["liters_tier"] = f.tier.fillna("standard")
    f["unit"] = [unit_name(m, k, s) for m, k, s in zip(f.cur_ml.fillna(f.bottle_ml), f.factor, f.source)]
    # unknown tier: left out of liters; held (restated items, ruling 01d amendment 3): no liters until the 01e ruling
    f["liters_per_unit"] = np.where(f.liters_tier.isin(["unknown", "held"]), np.nan, f.cur_ml.fillna(f.bottle_ml) * f.factor / 1000)
    f["price_per_unit"] = price[f.sid]
    f["liters_mean"] = f["mean"] * f.liters_per_unit
    f["cases_9l_mean"] = f.liters_mean / 9
    f["dollars_mean"] = f["mean"] * f.price_per_unit
    f["flag"] = f.series_id.map(FLAGS).fillna("")
    for it, note in FLAGS.items():                       # flag also when the item is a later number in the series
        hit = f.item_numbers.fillna("").str.split(" > ").map(lambda v: it in v) & (f.flag == "")
        f.loc[hit, "flag"] = note
    cols = ["series_id", "description", "unit", "category", "brand", "vendor_as_of_origin", "pool_class", "sbc_class",
            "origin", "target_month", "h", "mean"] + QC + ["price_per_unit", "dollars_mean", "liters_tier", "liters_per_unit",
            "liters_mean", "cases_9l_mean", "flag"]
    prod = f[cols].rename(columns={"mean": "units_mean", **{c: f"units_{c}" for c in QC}}).sort_values(["series_id", "h"])
    prod.to_csv(out / "forecast_live.csv", index=False)
    ser.to_csv(out / "product_list.csv", index=False)
    # levels: dollars first, covered liters, share of dollars covered, partial above 5% unknown (decision 52)
    f["usd_unknown"] = np.where(f.liters_tier.isin(["unknown", "held"]), f.dollars_mean, 0.0)
    f["usd_hand"] = np.where(f.brand_source == "hand-checked", f.dollars_mean, 0.0)
    lv = []
    for level, key in (("state", None), ("category", "category"), ("brand", "brand")):
        g = f.assign(state="Iowa").groupby([key or "state", "target_month", "h"])
        x = g.agg(dollars_mean=("dollars_mean", "sum"), liters_covered_mean=("liters_mean", "sum"),
                  usd_unknown=("usd_unknown", "sum"), usd_hand=("usd_hand", "sum"), products=("series_id", "nunique")).reset_index()
        x = x.rename(columns={key or "state": "name"}); x.insert(0, "level", level)
        lv.append(x)
    lv = pd.concat(lv, ignore_index=True)
    lv["share_of_dollars_with_liters"] = 1 - lv.usd_unknown / lv.dollars_mean
    lv["liters_label"] = np.where(lv.usd_unknown / lv.dollars_mean > 0.05, "partial", "")
    lv["cases_9l_covered_mean"] = lv.liters_covered_mean / 9
    lv["hand_checked_share"] = np.where(lv.level == "brand", lv.usd_hand / lv.dollars_mean, np.nan)
    lv["brand_label"] = np.where((lv.level == "brand") & (lv.hand_checked_share < 0.95), "hand-checked products only", "")
    # protocol section 2 direct ranges (s2levels.py), only where calibrated in time order (ruling-01e-amend item 4: no
    # uncalibrated ranges; those rows publish the total with no range)
    rc = [f"range_{c}" for c in QC]
    lf = base / "stage2" / "levels_forecasts.parquet"
    if lf.exists():
        R = pd.read_parquet(lf); R = R[R.o == o]
        R = R.rename(columns={c: f"range_{c}" for c in QC})[["level", "name", "h", "calibrated", *rc]]
        lv = lv.merge(R, on=["level", "name", "h"], how="left")
        lv.loc[lv.calibrated != True, rc] = np.nan
        lv["range_note"] = np.where(lv.calibrated == True, "direct ETS range, calibrated in time order; not forced to add up",
                                    "no range (not calibrated)")
        lv["sum_outside_own_50"] = (lv.calibrated == True) & ((lv.dollars_mean < lv.range_q25) | (lv.dollars_mean > lv.range_q75))
    else:
        for c in rc:
            lv[c] = np.nan
        lv["range_note"] = "no range (not built)"; lv["sum_outside_own_50"] = False
    lv = lv[["level", "name", "target_month", "h", "dollars_mean", *rc, "range_note", "sum_outside_own_50",
             "liters_covered_mean", "cases_9l_covered_mean",
             "share_of_dollars_with_liters", "liters_label", "hand_checked_share", "brand_label", "products"]]
    lv.to_csv(out / "forecast_live_levels.csv", index=False)
    json.dump({"live_unit_breaks": "a break detected after the freeze with pack ratio 3 or more that passes the continuity "
                                   "test is restated into the frozen unit for grading and shown beside the grade; a pack "
                                   "ratio under 3 is read by hand first (ruling 01b amendment item 7)",
               "grading_unit": "units as frozen (protocol section 10)"}, open(out / "grading_rules.json", "w"), indent=1)
    st = lv[lv.level == "state"]
    print(f"live forecast, layer {chosen}, origin {d.months[o]}: {prod.series_id.nunique():,} series; flagged {int((prod.flag != '').sum() / 3)}")
    print(st[["target_month", "dollars_mean", "liters_covered_mean", "share_of_dollars_with_liters", "liters_label"]].round(3).to_string(index=False))
