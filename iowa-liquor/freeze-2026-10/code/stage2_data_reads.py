"""Addendum 8 data reads (read-only): (1) zeros, negatives and blanks by year and column; (2) 30 repaired price lines
drawn with a fixed seed, with the item-month context needed to judge each repair by hand.
Usage: python data_reads.py <base>  ->  stage1/evidence_zero_neg_blank_by_year.csv, stage1/repaired_lines_sample30.txt"""
import sys
from pathlib import Path
import duckdb, pandas as pd
base = Path(sys.argv[1]); out = base / "stage1"
con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
num = ["pack", "bottle_volume_ml", "sales_bottles_recorded", "sales_dollars", "sales_dollars_raw", "state_bottle_cost_raw",
       "state_bottle_retail_raw", "sales_liters_raw"]
txt = ["invoice_id", "store_no_raw", "store_name", "city", "zip", "county_name", "category_code", "category_name",
       "vendor_number", "vendor_name", "item_no", "im_desc"]
sel = ["year(order_date) AS year", "COUNT(*) AS lines", "SUM(CASE WHEN order_date IS NULL THEN 1 ELSE 0 END) AS order_date_null"]
for c in num:
    sel += [f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS {c}_null", f"SUM(CASE WHEN {c} = 0 THEN 1 ELSE 0 END) AS {c}_zero",
            f"SUM(CASE WHEN {c} < 0 THEN 1 ELSE 0 END) AS {c}_neg"]
for c in txt:
    sel += [f"SUM(CASE WHEN {c} IS NULL OR trim(CAST({c} AS VARCHAR)) = '' THEN 1 ELSE 0 END) AS {c}_blank"]
prof = con.execute(f"SELECT {', '.join(sel)} FROM sales GROUP BY 1 ORDER BY 1").df()
prof.to_csv(out / "evidence_zero_neg_blank_by_year.csv", index=False)
nz = prof.drop(columns=["year", "lines"]).sum()
print("profile: columns with any null/zero/negative/blank: " + "; ".join(f"{k} {int(v):,}" for k, v in nz[nz > 0].items()))

rep = con.execute('''
WITH r AS (SELECT rowid AS rid, item_no, order_date, im_desc, sales_bottles_recorded AS b, state_bottle_retail_raw AS p_raw,
                  state_bottle_retail AS p_fix, sales_dollars_raw AS usd_raw, sales_dollars AS usd, dollars_source
           FROM sales WHERE price_repaired)
SELECT * FROM r ORDER BY hash(rid + 61) LIMIT 30''').df().sort_values(["order_date", "item_no"])
lines = [f"30 repaired price lines (fixed hash order, seed 61) of {con.execute('SELECT COUNT(*) FROM sales WHERE price_repaired').fetchone()[0]:,}"]
for r in rep.itertuples():
    ctx = con.execute('''SELECT state_bottle_retail_raw AS p, COUNT(*) AS n FROM sales
        WHERE item_no = ? AND date_trunc('month', order_date) = date_trunc('month', CAST(? AS DATE)) GROUP BY 1 ORDER BY n DESC LIMIT 6''',
        [r.item_no, r.order_date]).df()
    lines.append(f"{pd.Timestamp(r.order_date):%Y-%m-%d} {r.item_no} {str(r.im_desc)[:34]:34} btl {r.b:>4.0f} retail raw {r.p_raw:>7.2f} -> {r.p_fix:>7.2f} "
                 f"| $ raw {r.usd_raw:>9.2f} -> {r.usd:>9.2f} ({r.dollars_source}) | month prices: "
                 + ", ".join(f"{x.p:.2f} x{x.n}" for x in ctx.itertuples()))
(out / "repaired_lines_sample30.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"repaired lines sample: {len(rep)} -> stage1/repaired_lines_sample30.txt")
