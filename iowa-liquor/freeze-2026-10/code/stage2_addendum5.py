"""Addendum 5 checks before the freeze (judge verdict, decision 49). Read-only on the stage 1 database.
1) Units table evidence per carrier item: liters per recorded bottle in a pre-change month, the date the recorded size
   changed, the comparator (other item numbers with the same description; median dollars per ml) and the price ratio.
2a) Items with more than one recorded size: whole-multiple size changes of 2x or more where bottles per month and
   dollars per bottle run smoothly through the change (carrier candidates).
2b) Per top-20 brand: series whose trailing-12 dollars per liter is 4x or more the brand's dollar-weighted median.
3) Decision 49: share of each top-20 brand's trailing-12 dollars on hand-checked series, and the reverse check
   (the same vendors' other series whose description contains the brand name but are not mapped to the brand).
Detail goes to stage2/addendum5_*.csv; a short summary is printed.
Usage: python addendum5.py <base>"""
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from brand_map import BRANDS, norm
CARRIER_FACTOR = []      # decision 48 table withdrawn by decision 51 (liters tiers in units_tiers.py)

if __name__ == "__main__":
    base = Path(sys.argv[1]); out = base / "stage2"
    con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
    bm = pd.read_csv(out / "brand_map.csv", dtype={"series_id": str})
    top20 = pd.read_csv(out / "top20_brands.csv").brand.tolist()
    cf = pd.DataFrame(CARRIER_FACTOR, columns=["item_no", "k", "only_ml"])
    con.register("cf", cf)
    # item-month table: bottles, dollars, recorded size (modal by bottles)
    im = con.execute('''
        SELECT item_no, date_trunc('month', order_date)::DATE AS m, bottle_volume_ml AS ml,
               SUM(sales_bottles) AS b, SUM(sales_dollars) AS usd
        FROM sales WHERE sales_bottles > 0 GROUP BY 1, 2, 3''').df()
    im["item_no"] = im.item_no.astype(str)
    items = con.execute("SELECT item_no, d, ml AS item_ml, series_id FROM item_series").df()
    items["item_no"] = items.item_no.astype(str); items["series_id"] = items.series_id.astype(str)
    items["nd"] = items.d.map(norm)

    # 1) evidence for the units table (decision 48 table withdrawn by decision 51: nothing to list)
    if not CARRIER_FACTOR:
        print("1) units table evidence: decision 48 table withdrawn (decision 51); see units_tiers.py")
    ev = []
    for item, k, only_ml in CARRIER_FACTOR:
        x = im[im.item_no == item]
        sizes = x.groupby("ml").b.sum()
        chg = x[x.ml == only_ml].m.min() if only_ml is not None and len(sizes) > 1 else pd.NaT
        pre = x[(x.m < chg)] if pd.notna(chg) else x.iloc[0:0]
        pre_m = pre.m.max() if len(pre) else pd.NaT
        pre_row = pre[pre.m == pre_m]
        lpb_pre = float((pre_row.b * pre_row.ml).sum() / pre_row.b.sum() / 1e3) if len(pre_row) else np.nan
        last12 = x[x.m > x.m.max() - pd.DateOffset(months=12)]
        usd_per_ml = last12.usd.sum() / (last12.b * last12.ml).sum()
        desc = items.loc[items.item_no == item, "nd"].iloc[0]
        sib = items[(items.nd == desc) & (items.item_no != item)].item_no.tolist()
        s = im[im.item_no.isin(sib)]
        s12 = s[s.m > s.m.max() - pd.DateOffset(months=12)] if len(s) else s
        sib_usd_per_ml = (s12.usd.sum() / (s12.b * s12.ml).sum()) if len(s12) else np.nan
        ev.append(dict(item_no=item, description=desc, pack_factor=k, applies_to_ml=only_ml,
                       recorded_sizes="/".join(f"{int(a)}" for a in sizes.index),
                       size_change_month=None if pd.isna(chg) else str(chg.date()),
                       pre_change_month=None if pd.isna(pre_m) else str(pre_m.date()),
                       liters_per_bottle_pre_change=lpb_pre,
                       usd_per_bottle_t12=last12.usd.sum() / last12.b.sum(),
                       comparator_items=" ".join(sib[:6]), comparator_usd_per_ml=sib_usd_per_ml,
                       price_ratio_vs_comparator=usd_per_ml / sib_usd_per_ml if sib_usd_per_ml else np.nan))
    if ev:
        ev = pd.DataFrame(ev); ev.to_csv(out / "addendum5_units_evidence.csv", index=False)
        print("1) units table evidence:")
        print(ev[["item_no", "pack_factor", "recorded_sizes", "size_change_month", "pre_change_month",
                  "liters_per_bottle_pre_change", "usd_per_bottle_t12", "price_ratio_vs_comparator"]].round(3).to_string(index=False))

    # 2a) whole-multiple size changes with smooth bottles and price
    multi = im.groupby("item_no").ml.nunique(); multi = multi[multi > 1].index
    mm = im[im.item_no.isin(multi)].sort_values(["item_no", "m"])
    mm = mm.loc[mm.groupby(["item_no", "m"]).b.idxmax()]          # modal size per item-month
    rows = []
    for it, g in mm.groupby("item_no"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            a, b = g.ml[i - 1], g.ml[i]
            if a == b or min(a, b) <= 0:
                continue
            r = max(a, b) / min(a, b)
            if r < 2 or abs(r - round(r)) > 0.05:
                continue
            bef, aft = g.iloc[max(0, i - 3):i], g.iloc[i:i + 3]
            bpm = aft.b.mean() / bef.b.mean()
            ppb = (aft.usd.sum() / aft.b.sum()) / (bef.usd.sum() / bef.b.sum())
            rows.append(dict(item_no=it, month=str(g.m[i].date()), ml_from=a, ml_to=b, multiple=round(r),
                             bottles_ratio=bpm, price_ratio=ppb,
                             smooth=bool(0.5 <= bpm <= 2 and 0.67 <= ppb <= 1.5)))
    sc = pd.DataFrame(rows, columns=["item_no", "month", "ml_from", "ml_to", "multiple", "bottles_ratio", "price_ratio", "smooth"])
    sc = sc.merge(items[["item_no", "d", "series_id"]], on="item_no", how="left")
    sc["known"] = sc.item_no.isin(cf.item_no)
    sc.to_csv(out / "addendum5_size_changes.csv", index=False)
    print(f"\n2a) items with several sizes: {len(multi)}; whole-multiple changes >=2x: {len(sc)}; "
          f"smooth (bottles 0.5-2x, price 0.67-1.5x): {int(sc.smooth.sum())}, of which already in units table: "
          f"{int((sc.smooth & sc.known).sum())}")
    if len(sc):
        print(sc[sc.smooth][["item_no", "d", "month", "ml_from", "ml_to", "bottles_ratio", "price_ratio", "known"]]
              .round(2).head(25).to_string(index=False))

    # trailing-12 by series with corrected liters
    t12 = con.execute('''
        SELECT i.series_id, SUM(l.sales_dollars) AS usd, SUM(l.sales_bottles) AS b,
               SUM(l.sales_bottles * l.bottle_volume_ml * CASE WHEN cf.k IS NOT NULL AND (cf.only_ml IS NULL OR
                   cf.only_ml = l.bottle_volume_ml) THEN cf.k ELSE 1 END) / 1e3 AS liters
        FROM sales l JOIN item_series i USING (item_no) LEFT JOIN cf ON cf.item_no = l.item_no
        WHERE l.sales_bottles > 0 AND l.order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH
        GROUP BY 1''').df()
    t12["series_id"] = t12.series_id.astype(str)
    t = bm[["series_id", "description", "vendor", "brand", "brand_source"]].merge(t12, on="series_id", how="inner")
    t["usd_per_l"] = t.usd / t.liters

    # 2b) high dollars-per-liter outliers within each top-20 brand
    out2b = []
    for br in top20:
        g = t[(t.brand == br) & (t.liters > 0)].sort_values("usd_per_l")
        cw = g.usd.cumsum() / g.usd.sum()
        med = g.usd_per_l[cw >= 0.5].iloc[0]
        o = g[g.usd_per_l >= 4 * med].assign(brand_median_usd_per_l=med, ratio=lambda x: x.usd_per_l / med)
        out2b.append(o)
    o2 = pd.concat(out2b); o2["in_units_table"] = o2.series_id.isin(cf.item_no) | o2.series_id.isin(
        items[items.item_no.isin(cf.item_no)].series_id)
    o2.sort_values("usd", ascending=False).to_csv(out / "addendum5_price_outliers.csv", index=False)
    print(f"\n2b) series at >=4x their brand's dollar-weighted median $/L: {len(o2)} "
          f"(${o2.usd.sum():,.0f}, {int(o2.in_units_table.sum())} already in units table)")
    print(o2.sort_values("usd", ascending=False)[["series_id", "description", "brand", "usd", "ratio", "in_units_table"]]
          .round(1).head(30).to_string(index=False))

    # 3) decision 49 share on hand-checked series, and reverse check
    sh = t[t.brand.isin(top20)].groupby("brand").apply(
        lambda g: pd.Series({"usd_t12": g.usd.sum(), "hand_checked_share": g.usd[g.brand_source == "hand-checked"].sum() / g.usd.sum(),
                             "rule_only_series": int((g.brand_source == "rule only").sum())}), include_groups=False)
    sh = sh.reindex(top20); sh["passes_95"] = sh.hand_checked_share >= 0.95
    sh.to_csv(out / "addendum5_brand_hand_share.csv")
    print("\n3) decision 49, share of trailing-12 dollars on hand-checked series:")
    print(sh.assign(hand_checked_share=lambda x: (100 * x.hand_checked_share).round(1), usd_t12=lambda x: x.usd_t12.round(0))
          .to_string())
    keys = {}
    for k, v in BRANDS.items():
        keys.setdefault(v, []).append(k)
    rev = []
    for br in top20:
        vend = set(t[t.brand == br].vendor.dropna())
        g = t[t.vendor.isin(vend) & (t.brand != br)]
        hit = g[g.description.map(lambda d: any(f" {k} " in f" {norm(d)} " for k in keys.get(br, [])))]
        rev.append(hit.assign(searched_brand=br))
    rv = pd.concat(rev); rv.to_csv(out / "addendum5_reverse_check.csv", index=False)
    print(f"\n3b) reverse check: same-vendor series naming a top-20 brand but mapped elsewhere: {len(rv)} (${rv.usd.sum():,.0f})")
    print(rv.sort_values("usd", ascending=False)[["series_id", "description", "searched_brand", "brand", "usd"]]
          .round(0).head(25).to_string(index=False))
    # rule-only series per failing brand, for the hand check (written, not printed)
    fail = sh[~sh.passes_95].index
    t[t.brand.isin(fail) & (t.brand_source == "rule only")].sort_values(["brand", "usd"], ascending=[True, False]) \
        .to_csv(out / "addendum5_rule_only_for_hand_check.csv", index=False)
