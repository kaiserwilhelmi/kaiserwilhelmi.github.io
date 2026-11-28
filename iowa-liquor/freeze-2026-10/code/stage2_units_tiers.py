"""Decision 51 (protocol 1.10 section 1): liters in three evidence tiers per item and period. Read-only on the database.
- proven: the state's own records give the factor (liters per unit = recorded ml x factor):
    (a) size history: a whole-multiple change of recorded size of 2x or more with bottles and price per bottle smooth
        through it (bottles 0.5-2x, price 0.67-1.5x, 3 months either side); rows at the smaller size take
        larger / smaller. Genuine size changes found by hand are excluded (Foundry Gin 375 to 750, the Cedar Ridge barrel,
        Bruichladdich 4500).
    (b) a unit break applied from the frozen table (stage1/unit_breaks.csv): the restated unit is a pack of
        max(1, old pack / new pack) recorded bottles; chained with (a).
  Check: trailing-12 dollars per liter within 0.5x to 3x the brand's dollar-weighted median, else listed for a hand read.
- unknown: dollars per liter 4x or more the brand median with no size history or unit break, and a recorded size of
  200 ml or less or a description that marks a pack; no factor is guessed and these series are left out of liters.
- standard: everything else, liters = units x recorded ml. Full-size series over 4x stay standard; the largest are
  listed for a hand read.
Brand from stage2/brand_map.csv; a series with no brand uses its category median.
Outputs: stage2/units_lines_factor.parquet (item_no, ml, factor, tier source), stage2/units_series_t12.csv,
stage2/units_tiers_hand_read.csv, stage2/units_table.csv (frozen-package table). Usage: python units_tiers.py <base>"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")   # MKL's OpenMP layer crashes in this env (0xc06d007f); set before numpy loads
import re, sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd

GENUINE = [r"\bFOUNDRY\b.*\bGIN\b", r"\bCEDAR RIDGE\b.*\bBARREL\b", r"\bBRUICHLADDICH\b"]
PACK_WORDS = r"\b(\d+\s?PK|PACK|PK|SLEEVE|SLEEVES|BUCKET|TRIO|SAMPLER|VARIETY|CUBE|TUBE|TRAY|PARTY|DISPLAY|MULTI)\b"

def size_changes(con):
    im = con.execute('''SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS m, bottle_volume_ml AS ml,
                               SUM(sales_bottles_recorded) AS b, SUM(sales_dollars) AS usd, MODE(im_desc) AS d
                        FROM sales WHERE sales_bottles_recorded > 0 AND bottle_volume_ml > 0 GROUP BY 1, 2, 3''').df()
    multi = im.groupby("item_no").ml.nunique(); multi = multi[multi > 1].index
    mm = im[im.item_no.isin(multi)].sort_values(["item_no", "m", "b"]).groupby(["item_no", "m"]).tail(1)
    rows = []
    for it, g in mm.groupby("item_no"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            a, b = g.ml[i - 1], g.ml[i]
            if a == b:
                continue
            r = max(a, b) / min(a, b)
            if r < 2 or abs(r - round(r)) > 0.05:
                continue
            bef, aft = g.iloc[max(0, i - 3):i], g.iloc[i:i + 3]
            br = aft.b.mean() / bef.b.mean(); pr = (aft.usd.sum() / aft.b.sum()) / (bef.usd.sum() / bef.b.sum())
            genuine = any(re.search(p, str(g.d[i])) for p in GENUINE)
            rows.append(dict(item_no=it, month=g.m[i], ml_from=a, ml_to=b, multiple=round(r), bottles_ratio=br, price_ratio=pr,
                             smooth=bool(0.5 <= br <= 2 and 0.67 <= pr <= 1.5), genuine_by_hand=genuine, d=g.d[i]))
    return pd.DataFrame(rows, columns=["item_no", "month", "ml_from", "ml_to", "multiple", "bottles_ratio", "price_ratio",
                                       "smooth", "genuine_by_hand", "d"])

if __name__ == "__main__":
    base = Path(sys.argv[1]); out = base / "stage2"
    con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
    sc = size_changes(con)
    used = sc[sc.smooth & ~sc.genuine_by_hand]
    # (a) size factor per item and recorded ml: rows at the smaller size of a proven change take larger / smaller
    sf = used.assign(small=lambda x: x[["ml_from", "ml_to"]].min(1), large=lambda x: x[["ml_from", "ml_to"]].max(1))
    sf = sf.groupby(["item_no", "small"]).large.max().reset_index().rename(columns={"small": "ml"})
    sf["size_factor"] = sf.large / sf.ml
    # (b) unit breaks applied from the frozen table: the restated unit is a pack of max(1, old / new) recorded bottles
    ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str}, parse_dates=["month"])
    ap["pack_of"] = np.maximum(1.0, ap.pack_old / ap.pack_new)
    ubf = ap.groupby("item_no").pack_of.prod().rename("break_factor").reset_index()
    # line groups: item number (incl. ~pre parts) x recorded ml; the ~pre part of a cut item keeps the old unit
    g = con.execute('''SELECT s.item_no, regexp_replace(s.item_no, '~pre.*', '') AS base_item, i.series_id, s.bottle_volume_ml AS ml,
                              MODE(s.im_desc) AS d, ANY_VALUE(i.category_name) AS category,
                              SUM(s.sales_bottles) AS units, SUM(s.sales_dollars) AS usd,
                              SUM(CASE WHEN s.order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH THEN s.sales_bottles ELSE 0 END) AS units_t12,
                              SUM(CASE WHEN s.order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH THEN s.sales_dollars ELSE 0 END) AS usd_t12,
                              MIN(s.order_date) AS first_order, MAX(s.order_date) AS last_order
                       FROM sales s JOIN item_series i USING (item_no) WHERE s.sales_bottles > 0 GROUP BY 1, 2, 3, 4''').df()
    g = g.merge(sf[["item_no", "ml", "size_factor"]].rename(columns={"item_no": "base_item"}), on=["base_item", "ml"], how="left")
    g = g.merge(ubf.rename(columns={"item_no": "base_item"}), on="base_item", how="left")
    # pre-break part of a cut item keeps the OLD unit: a pack of max(1, new pack / old pack) recorded bottles
    lastb = ap.sort_values("month").groupby("item_no").tail(1).set_index("item_no")
    pre = g.item_no.str.contains("~pre")
    g.loc[pre, "break_factor"] = np.maximum(1.0, (lastb.pack_new / lastb.pack_old).reindex(g.loc[pre, "base_item"]).to_numpy())
    g.loc[pre & (g.break_factor == 1), "break_factor"] = np.nan
    g["factor"] = g.size_factor.fillna(1) * g.break_factor.fillna(1)
    g["source"] = np.select([g.size_factor.notna() & g.break_factor.notna(), g.size_factor.notna(), g.break_factor.notna()],
                            ["size history + unit break", "size history", "unit break"], "")
    g["liters_t12"] = g.units_t12 * g.ml * g.factor / 1000
    # series level, trailing 12, with brand
    bm = pd.read_csv(out / "brand_map.csv", dtype={"series_id": str})[["series_id", "brand", "brand_source"]]
    s = (g.groupby("series_id").agg(usd_t12=("usd_t12", "sum"), liters_t12=("liters_t12", "sum"), units_t12=("units_t12", "sum"),
                                    ml=("ml", "max"), d=("d", "first"), category=("category", "first"),
                                    has_size=("source", lambda v: v.str.contains("size history").any()),
                                    has_break=("source", lambda v: v.str.contains("unit break").any()),
                                    source=("source", lambda v: "; ".join(sorted(set(v) - {""}))))
           .reset_index().merge(bm, on="series_id", how="left"))
    s = s[s.usd_t12 > 0].copy()
    # category: the same deterministic rule as s2common.Data (most bottles, then lines, then name). ANY_VALUE plus
    # "first" gave a different category between runs for series with several (found at the ruling-04 rerun)
    attr = con.execute('''WITH c AS (SELECT i.series_id, s.category_name AS category, SUM(s.sales_bottles) AS b, COUNT(*) AS n
                                     FROM sales s JOIN item_series i USING (item_no)
                                     WHERE s.sales_bottles > 0 AND trim(COALESCE(s.category_name, '')) <> '' GROUP BY 1, 2),
                          r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY b DESC, n DESC, category) AS k FROM c)
                          SELECT series_id, category FROM r WHERE k = 1''').df().set_index("series_id").category
    s["category"] = s.series_id.map(attr).fillna(s.category)
    # description, same rule (MODE and "first" broke ties differently between runs); sums rounded to cents and
    # microliters so that summation order cannot move a series across a screen threshold
    desc = con.execute('''WITH c AS (SELECT i.series_id, s.im_desc AS d, SUM(s.sales_bottles) AS b, COUNT(*) AS n
                                     FROM sales s JOIN item_series i USING (item_no)
                                     WHERE s.sales_bottles > 0 AND s.im_desc IS NOT NULL GROUP BY 1, 2),
                          r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY b DESC, n DESC, d) AS k FROM c)
                          SELECT series_id, d FROM r WHERE k = 1''').df().set_index("series_id").d
    s["d"] = s.series_id.map(desc).fillna(s.d)
    s["usd_t12"] = s.usd_t12.round(2); s["liters_t12"] = s.liters_t12.round(6)
    s["usd_per_l"] = s.usd_t12 / s.liters_t12
    s["lpu"] = s.liters_t12 / s.units_t12                      # liters per current unit as the rule computes it
    isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
    restated = set(isr.reindex(ap[ap.outcome == "restated"].item_no).dropna())
    s["restated"] = s.series_id.isin(restated)
    def wmed(x):
        x = x[np.isfinite(x.usd_per_l)].sort_values("usd_per_l"); c = x.usd_t12.cumsum() / x.usd_t12.sum()
        return x.usd_per_l[c >= 0.5].iloc[0] if len(x) else np.nan
    # decision 66 (ruling 01e): a unit break alone never proves liters; proven needs the state's own size history.
    # A restated series is proven only with size history AND (judge's Addendum 13) a price check against a proven
    # sibling of the same brand in the same month within 5%, AND bottles and price per bottle level within 10% across
    # its 600 -> 50 ml relabel. Price is a check, never a source of liters.
    cand = s[s.restated & s.has_size].copy()
    sm = con.execute("SELECT series_id, month_start AS m, bottles, dollars_retail AS usd FROM series_month WHERE bottles > 0").df()
    sm = sm[sm.series_id.isin(cand.series_id)].merge(cand[["series_id", "lpu", "brand"]], on="series_id")
    sm["usd_per_l"] = sm.usd / (sm.bottles * sm.lpu)
    chk = []
    for r in cand.itertuples():
        mine = sm[sm.series_id == r.series_id].set_index("m").usd_per_l
        sib = sm[(sm.brand == r.brand) & (sm.series_id != r.series_id)]
        best = None
        for sid, gs in sib.groupby("series_id"):
            com = mine.index.intersection(gs.m)
            if len(com):
                mm = com.max(); rat = mine[mm] / gs.set_index("m").usd_per_l[mm]
                if best is None or abs(rat - 1) < abs(best[2] - 1):
                    best = (sid, mm, rat)
        # relabel test: 3 months each side of the item's size relabel (recorded bottles, dollars per bottle)
        its = [i for i, sid in isr.items() if sid == r.series_id]
        rl = used[used.item_no.isin(its)].sort_values("month")
        rel = (np.nan, np.nan, None)
        if len(rl):
            mo = pd.Timestamp(rl.month.iat[0])
            q = con.execute("""SELECT CAST(date_trunc('month', order_date) AS DATE) AS m, SUM(sales_bottles_recorded) AS b, SUM(sales_dollars) AS usd
                FROM sales WHERE item_no IN (SELECT UNNEST(?::VARCHAR[])) AND sales_bottles_recorded > 0 GROUP BY 1 ORDER BY 1""", [its]).df()
            q["m"] = pd.to_datetime(q.m); i = q.index[q.m >= mo][0]
            bef, aft = q.iloc[max(0, i - 3):i], q.iloc[i:i + 3]
            rel = (aft.b.mean() / bef.b.mean(), (aft.usd.sum() / aft.b.sum()) / (bef.usd.sum() / bef.b.sum()), mo.strftime("%Y-%m"))
        chk.append(dict(series_id=r.series_id, brand=r.brand, lpu=r.lpu, sibling=best[0] if best else None,
                        sibling_month=str(best[1])[:7] if best else None, price_per_l_vs_sibling=best[2] if best else np.nan,
                        relabel_month=rel[2], relabel_bottles_ratio=rel[0], relabel_price_ratio=rel[1]))
    ck = pd.DataFrame(chk, columns=["series_id", "brand", "lpu", "sibling", "sibling_month", "price_per_l_vs_sibling",
                                    "relabel_month", "relabel_bottles_ratio", "relabel_price_ratio"])
    ck["price_ok"] = (ck.price_per_l_vs_sibling - 1).abs() <= 0.05
    ck["relabel_ok"] = ck.relabel_bottles_ratio.between(0.9, 1.1) & ck.relabel_price_ratio.between(0.9, 1.1)
    # a sibling only counts if it is itself proven: iterate until stable
    ok = set(ck.series_id[ck.price_ok & ck.relabel_ok])
    while True:
        new_ok = {r.series_id for r in ck.itertuples() if r.series_id in ok and r.sibling in ok}
        if new_ok == ok:
            break
        ok = new_ok
    ck["proven"] = ck.series_id.isin(ok)
    ck.to_csv(out / "units_decision66_checks.csv", index=False)
    small_or_pack = (s.ml <= 200) | s.d.fillna("").str.contains(PACK_WORDS, regex=True)
    base_tier = np.select([s.has_break & ~s.has_size,                       # unit break alone: unknown
                           s.restated & s.has_size & ~s.series_id.isin(ok),  # restated, check failed: unknown
                           s.has_size],                                      # size history (incl. passing restated): proven
                          ["unknown", "unknown", "proven"], "standard")
    s["tier"] = base_tier
    s["group"] = s.brand.fillna("category: " + s.category.fillna("?"))
    std = s[s.tier == "standard"]
    medb = std.groupby("group").apply(wmed, include_groups=False).rename("group_median_usd_per_l")
    medc = s[s.tier != "unknown"].groupby("category").apply(wmed, include_groups=False).rename("category_median_usd_per_l")
    s = s.merge(medb, left_on="group", right_index=True, how="left").merge(medc, left_on="category", right_index=True, how="left")
    s["ratio"] = s.usd_per_l / s.group_median_usd_per_l
    s["ratio_category"] = s.usd_per_l / s.category_median_usd_per_l
    flag_c = (s.ratio_category < 0.25) | (s.ratio_category > 4)              # judge's Addendum 13 screen, fixed
    small_or_pack = (s.ml <= 200) | s.d.fillna("").str.contains(PACK_WORDS, regex=True)
    s["category_screen_flag"] = flag_c
    s.loc[(s.tier == "standard") & (((s.ratio >= 4) & small_or_pack) | (flag_c & small_or_pack)), "tier"] = "unknown"
    s["hand_read"] = np.select([(s.tier == "proven") & ~s.ratio.between(0.5, 3),
                                (s.tier == "standard") & flag_c, (s.tier == "standard") & (s.ratio >= 4)],
                               ["proven outside 0.5-3x brand median", "category screen flag (not small, no pack mark)",
                                "full-size over 4x brand median"], "")
    # ruling-04 item 5: flagged series not hand read by the freeze default to unknown (none were read: HAND_READ_DONE empty)
    HAND_READ_DONE = set()
    unread = (s.tier == "standard") & flag_c & ~s.series_id.isin(HAND_READ_DONE)
    s["unread_flag_default"] = unread
    s.loc[unread, "tier"] = "unknown"
    s["liters_computed_t12"] = s.liters_t12
    s.loc[s.tier == "unknown", "liters_t12"] = np.nan
    s.sort_values("usd_t12", ascending=False).to_csv(out / "units_series_t12.csv", index=False)
    s[s.hand_read != ""].sort_values("usd_t12", ascending=False).to_csv(out / "units_tiers_hand_read.csv", index=False)
    # the frozen-package units table: one row per item number and recorded size with a factor other than 1
    tab = g[g.factor != 1][["item_no", "series_id", "ml", "factor", "source", "first_order", "last_order", "d"]].copy()
    tab["liters_per_unit"] = tab.ml * tab.factor / 1000
    tab = tab.merge(s[["series_id", "tier", "ratio", "hand_read"]], on="series_id", how="left")
    tab.to_csv(out / "units_table.csv", index=False)
    unk = s[s.tier == "unknown"][["series_id", "tier"]]
    g.merge(unk, on="series_id", how="left").fillna({"tier": ""})[["item_no", "series_id", "ml", "factor", "source", "tier"]] \
        .to_parquet(out / "units_lines_factor.parquet", index=False)
    # reports for 03-tuning.md (ruling 01e amendment items 2a, 2b, 13, 14)
    tot = s.usd_t12.sum()
    small_std = s[(s.tier == "standard") & (s.ml <= 200)]
    size_only = s[(s.tier == "proven") & s.has_size & ~s.has_break]
    print(f"decision 66 checks (restated with size history): {len(ck)}; proven {int(ck.proven.sum())}: {sorted(ok)}")
    print(f"2a: standard-tier series at 200 ml or less: {len(small_std)} (${small_std.usd_t12.sum():,.0f}, {100 * small_std.usd_t12.sum() / tot:.2f}%)")
    print(f"2b: proven with size history and no unit break: {len(size_only)} (${size_only.usd_t12.sum():,.0f}, {100 * size_only.usd_t12.sum() / tot:.2f}%)")
    print(f"13: category screen flags {int(flag_c.sum())} (${s.usd_t12[flag_c].sum():,.0f}); moved to unknown by it "
          f"{int(((s.tier == 'unknown') & flag_c & small_or_pack).sum())}; listed for a hand read {int(((s.tier == 'standard') & flag_c).sum())} "
          f"(${s.usd_t12[(s.tier == 'standard') & flag_c].sum():,.0f})")
    left = s[s.tier == "unknown"]
    print(f"14: liters cover {100 * (1 - left.usd_t12.sum() / tot):.2f}% of trailing-12 dollars; series left out {len(left)}")
    # comparison with the Addendum 5 list of high dollars-per-liter series (top-20 brands)
    a5 = out / "addendum5_price_outliers.csv"
    cmp = ""
    if a5.exists():
        o = pd.read_csv(a5, dtype={"series_id": str}).merge(s[["series_id", "tier", "hand_read"]], on="series_id", how="left")
        cmp = (f"Addendum 5 high-$/L list: {len(o)} series; now standard {int((o.tier == 'standard').sum())}, proven "
               f"{int((o.tier == 'proven').sum())}, unknown {int((o.tier == 'unknown').sum())}")
    tot = s.usd_t12.sum()
    by = s.groupby("tier").agg(series=("series_id", "size"), usd=("usd_t12", "sum"), liters=("liters_t12", "sum"))
    by["pct_usd"] = (100 * by.usd / tot).round(2)
    print(f"size changes: {len(sc)} whole-multiple 2x+, smooth {int(sc.smooth.sum())}, genuine by hand {int(sc.genuine_by_hand.sum())}, "
          f"used {len(used)}; unit-break items {len(ubf)}")
    print("tiers (series with trailing-12 sales):"); print(by.round(0).to_string())
    print(f"hand reads: proven outside 0.5-3x {int((s.hand_read == 'proven outside 0.5-3x').sum())}, full-size over 4x "
          f"{int((s.hand_read == 'full-size over 4x').sum())}; {cmp}")
