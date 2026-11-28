"""Builds 01_stage1_demand_tables.ipynb. Each code cell is preceded by a plain
'what this block does and why' markdown note."""
import nbformat as nbf, sys

cells = []
def md(s): cells.append(nbf.v4.new_markdown_cell(s.strip()))
def code(s): cells.append(nbf.v4.new_code_cell(s.strip()))

md(r"""
# Iowa liquor orders forecast. Stage 1: cleaned orders, monthly product table, checks

**Data:** Iowa Liquor Sales, 2012 to 2026 (Iowa Data Hub datasets 1249 to 1263), published by the Iowa Department of
Revenue, Alcohol & Tax Operations Division, Alcohol Operations Bureau, on data.iowa.gov, under CC BY 4.0. This
notebook changes the published data (duplicate parts dropped, truncated prices repaired, volume recomputed); every
change is listed and measured below.

**What the rows are:** each row is a licensed store's order from the state, which is the wholesaler in Iowa. The
industry calls these figures "warehouse depletions" (NABCA). They are orders the state filled, so a product that was
short or rationed shows what was shipped, not what stores wanted. We forecast **expected Iowa store orders** per
product per month, statewide, and add products up to brand, category and state totals.

**What this notebook produces**
1. A clean, typed table of every order line, with data-quality checks and the evidence the review asked for.
2. The monthly product table, the main input to the forecasts: bottles (the target), liters, 9-liter cases, physical
   cases and dollars, zero months filled from each item's first order month to the last data month.
3. A statewide order-day calendar (weekdays less Iowa state holidays), checked against the data.
4. A test of whether the last month in the file (October 2026) is complete.
5. Monthly demand classes at the last origin (Syntetos-Boylan-Croston convention) and history lengths.
6. Side tables for later views: weekly product demand (for a later "how much will Iowa pull" view), product and
   store attributes, county and store-by-category tables.

The SQL runs in DuckDB and is written so the same queries run in BigQuery; the few lines that differ are kept in one
small "dialect" block (section 7).

**How to run:** open in JupyterLab from the Miniforge env `ds`
(`<home>\miniforge3\Scripts\activate ds`, then `jupyter lab`). Run top to bottom.
""")

md(r"""
## 1. Setup
**What:** imports, folder paths and the few settings this stage uses.
**Why:** the data lives in `C:\ds\iowa-liquor`, outside OneDrive, so 8 GB isn't synced to the cloud. `raw/` holds the
state's zips exactly as downloaded, `parquet/` holds one compressed file per year made from them (by
`00_download_and_pack.py`), and `stage1/` holds what this notebook makes. Setting the `IOWA_DIR` environment
variable points the notebook somewhere else; the cloud copy of this run uses that.

`CLASS_START` / `CLASS_END` set the window used for the demand and ABC classes. The default is 2024-2025: the two
most recent full years *before* the frozen test period (Jan-Oct 2026), so the classes that steer model choice never
see test data.
""")
code(r"""
import os
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

BASE = Path(os.environ.get("IOWA_DIR", r"C:\ds\iowa-liquor"))
PARQUET = BASE / "parquet"
OUT = BASE / "stage1"
OUT.mkdir(parents=True, exist_ok=True)

CLASS_START, CLASS_END = "2024-01-01", "2025-12-31"   # window for SBC and ABC classes

pd.set_option("display.width", 160)
print("duckdb", duckdb.__version__, "| pandas", pd.__version__, "| data folder:", BASE)
""")

md(r"""
## 2. Check the input files against the manifest
**What:** lists the yearly Parquet files and recomputes each one's SHA-256 fingerprint, then compares it with
`manifest.csv`, which was written when the files were made from the state's zips.
**Why:** a matching fingerprint proves the file is byte-for-byte the one made from the download, so every number
below traces back to the state's published files. The manifest also records each zip's own fingerprint.
""")
code(r"""
import hashlib
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

manifest = pd.read_csv(BASE / "manifest.csv")
files = sorted(PARQUET.glob("sales_*.parquet"))
check = pd.DataFrame({"file": [f.name for f in files], "sha256_now": [sha256(f) for f in files]})
m = manifest[["year", "csv_rows", "parquet_sha256"]].assign(file=lambda d: "sales_" + d.year.astype(str) + ".parquet")
check = check.merge(m, on="file", how="outer")
check["matches"] = check.sha256_now == check.parquet_sha256
print(check.matches.sum(), "of", len(check), "files match the manifest")
check[["file", "csv_rows", "matches"]]
""")

md(r"""
## 3. Load every year into DuckDB, as text
**What:** opens a DuckDB database file and loads all yearly files into one table, `raw_all`, keeping every value as
text plus the name of the CSV part each row came from.
**Why:** loading as text first means nothing is silently dropped or mis-typed; we convert types ourselves in step 5,
where problems show up as counts. Keeping the part name lets us trace any row back to the state's file.
""")
code(r"""
con = duckdb.connect(str(OUT / "iowa_liquor.duckdb"))
glob = (PARQUET / "sales_*.parquet").as_posix()
con.execute(f"CREATE OR REPLACE TABLE raw_all AS SELECT * FROM read_parquet('{glob}')")
print(f"{con.execute('SELECT COUNT(*) FROM raw_all').fetchone()[0]:,} rows loaded")
con.execute("SELECT * FROM raw_all LIMIT 3").df().T
""")

md(r"""
## 4. The state's yearly files repeat some rows
**What:** for each CSV part, counts how many of its rows already appear in an *earlier* part of the same year.
**Why:** the yearly files add up to 37,208,488 rows, but the state's combined table has 35,287,731. This check finds
where the extra 1,920,757 rows come from instead of assuming. If a whole part is a copy of an earlier part, keeping
it would double that slice of demand. Rows that repeat *within* one part are left alone: the state's own total
includes them, so they look like genuine repeated order lines.
""")
code(r"""
part_check = con.execute('''
WITH r AS (
    SELECT source_part, regexp_extract(source_part, '_(20[0-9][0-9])_', 1) AS yr,
           md5(CAST(ROW(*COLUMNS(* EXCLUDE (source_part))) AS VARCHAR)) AS h
    FROM raw_all
),
per_part AS (SELECT source_part, yr, h, COUNT(*) AS n FROM r GROUP BY ALL)
SELECT a.source_part, a.yr AS year, SUM(a.n) AS rows,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM per_part b
                             WHERE b.h = a.h AND b.yr = a.yr AND b.source_part < a.source_part)
                THEN a.n ELSE 0 END) AS rows_in_earlier_part
FROM per_part a
GROUP BY a.source_part, a.yr ORDER BY a.source_part
''').df()
part_check["share_repeated"] = part_check.rows_in_earlier_part / part_check.rows
part_check[part_check.rows_in_earlier_part > 0]
""")

md(r"""
**Decision:** a part where every row already appears in an earlier part of the same year is a duplicate export and
is dropped (the earlier copy stays). The cell below builds that list from the check above (it is not typed in by hand) and confirms the
remaining total equals the state's combined table.
""")
code(r"""
dup_parts = part_check.loc[part_check.share_repeated == 1.0, "source_part"].tolist()
print("dropped parts:", dup_parts)
con.execute("CREATE OR REPLACE TABLE dropped_parts AS SELECT unnest(?::VARCHAR[]) AS source_part", [dup_parts])
kept = con.execute("SELECT COUNT(*) FROM raw_all WHERE source_part NOT IN (SELECT source_part FROM dropped_parts)").fetchone()[0]
print(f"rows kept: {kept:,}  | state's combined table: 35,287,731  | match: {kept == 35_287_731}")
""")

md(r"""
## 5. Type the columns
**What:** builds `sales`, a typed copy without the duplicate parts: dates as dates, numbers as numbers, IDs as text.
**Why:** `TRY_CAST` returns NULL instead of crashing on a bad value, and section 6 counts those NULLs, so a bad date
or number becomes a visible data-quality number. Item and store numbers stay as text because they are labels, not
quantities. Dollar fields are stripped of "$" and "," in case a year was exported with them.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE sales AS
SELECT
    invoice_id,
    COALESCE(TRY_CAST(ordered_on AS DATE), TRY_CAST(try_strptime(ordered_on, '%m/%d/%Y') AS DATE)) AS order_date,
    COALESCE(NULLIF(ltrim(trim(store_no), '0'), ''), '0') AS store_no, store_no AS store_no_raw,
    store_name, store_address, store_city AS city, store_zip_code AS zip, county_fips_code AS county_fips,
    upper(trim(county_name)) AS county_name,
    category_code, category_name,
    vendor_number, vendor_name,
    trim(item_no) AS item_no, im_desc,
    TRY_CAST(pack AS INTEGER)                 AS pack,
    TRY_CAST(bottle_volume_ml AS DOUBLE)      AS bottle_volume_ml,
    TRY_CAST(replace(replace(state_bottle_cost, '$', ''), ',', '') AS DOUBLE)   AS state_bottle_cost,
    TRY_CAST(replace(replace(state_bottle_retail, '$', ''), ',', '') AS DOUBLE) AS state_bottle_retail,
    TRY_CAST(sales_bottles AS INTEGER)        AS sales_bottles,
    TRY_CAST(replace(replace(sales_dollars, '$', ''), ',', '') AS DOUBLE)       AS sales_dollars,
    TRY_CAST(sales_liters AS DOUBLE)          AS sales_liters,
    TRY_CAST(sales_gallons AS DOUBLE)         AS sales_gallons,
    source_part
FROM raw_all
WHERE source_part NOT IN (SELECT source_part FROM dropped_parts)
''')
con.execute("SELECT * FROM sales LIMIT 3").df()
""")

md(r"""
## 6. Data-quality checks
**What:** a set of checks, each printed as a number, before we build anything on the data.
**Why:** forecasts are only as good as the history. These checks catch the usual problems in order data:
values that failed to convert, duplicate lines, returns (negative bottles), and columns that don't mean what
their labels say. The state's own column descriptions for pack, bottle volume and bottles sold are swapped,
so check 6d tests the columns against each other instead of trusting the labels.

**6a. Row count, date range, failed conversions.** The state's combined table has 35,287,731 rows (Jan 2 2012 to Oct 29 2026).
""")
code(r"""
dq = con.execute('''
SELECT
    COUNT(*)                                             AS rows_loaded,
    MIN(order_date)                                      AS first_date,
    MAX(order_date)                                      AS last_date,
    SUM(CASE WHEN order_date IS NULL THEN 1 ELSE 0 END)          AS bad_date,
    SUM(CASE WHEN sales_bottles IS NULL THEN 1 ELSE 0 END)       AS bad_bottles,
    SUM(CASE WHEN state_bottle_cost IS NULL THEN 1 ELSE 0 END)   AS bad_cost,
    SUM(CASE WHEN item_no IS NULL OR item_no = '' THEN 1 ELSE 0 END) AS missing_item,
    COUNT(DISTINCT item_no)                              AS items,
    COUNT(DISTINCT store_no)                             AS stores,
    COUNT(DISTINCT vendor_number)                        AS vendors
FROM sales
''').df().T
dq
""")

md(r"""
**6b. Duplicates.** Each order line should have its own invoice line ID; fully identical rows would double-count demand.
""")
code(r"""
con.execute('''
SELECT
    (SELECT COUNT(*) FROM sales) - (SELECT COUNT(DISTINCT invoice_id) FROM sales)  AS repeated_invoice_ids,
    (SELECT COUNT(*) FROM sales) - (SELECT COUNT(*) FROM (SELECT DISTINCT * EXCLUDE (source_part) FROM sales)) AS fully_identical_rows
''').df()
""")

md(r"""
**6c. Returns and zero lines.** Negative bottles are returns or corrections, not demand.
**Decision:** demand = bottles on lines with bottles > 0. Returns are counted here and left out of demand,
because a return doesn't tell the warehouse anything about what to stock next week, and netting them would
put negative weeks into the history. (Their share is small; this cell shows how small.)
""")
code(r"""
con.execute('''
SELECT
    SUM(CASE WHEN sales_bottles > 0 THEN 1 ELSE 0 END)  AS positive_lines,
    SUM(CASE WHEN sales_bottles = 0 THEN 1 ELSE 0 END)  AS zero_lines,
    SUM(CASE WHEN sales_bottles < 0 THEN 1 ELSE 0 END)  AS negative_lines,
    SUM(CASE WHEN sales_bottles < 0 THEN sales_bottles ELSE 0 END) * 1.0
      / NULLIF(SUM(CASE WHEN sales_bottles > 0 THEN sales_bottles ELSE 0 END), 0) AS returned_share_of_bottles,
    SUM(CASE WHEN state_bottle_cost <= 0 THEN 1 ELSE 0 END) AS nonpositive_cost_lines
FROM sales
''').df().T
""")

md(r"""
**6d. Do the columns mean what we think?** If `sales_bottles` really is bottles and `bottle_volume_ml` really is
the bottle size, then bottles × ml / 1000 should equal `sales_liters`, and bottles × `state_bottle_retail`
should equal `sales_dollars`. We count the lines that match within rounding.
""")
code(r"""
con.execute('''
SELECT
    AVG(CASE WHEN ABS(sales_bottles * bottle_volume_ml / 1000.0 - sales_liters) <= 0.02 THEN 1.0 ELSE 0.0 END) AS liters_match_share,
    AVG(CASE WHEN ABS(sales_bottles * state_bottle_retail - sales_dollars) <= 0.02 THEN 1.0 ELSE 0.0 END)     AS dollars_match_share,
    AVG(CASE WHEN state_bottle_retail >= state_bottle_cost THEN 1.0 ELSE 0.0 END)                              AS retail_ge_cost_share
FROM sales
WHERE sales_bottles <> 0
''').df().T
""")

md(r"""
**6e. Is an item number one product?** If an item number carries several bottle sizes or vendors, it isn't a
single stock-keeping unit and we'd need a different product key.
""")
code(r"""
con.execute('''
WITH per_item AS (
    SELECT item_no,
           COUNT(DISTINCT bottle_volume_ml) AS sizes,
           COUNT(DISTINCT pack)             AS packs,
           COUNT(DISTINCT vendor_number)    AS vendors,
           COUNT(DISTINCT im_desc)          AS descriptions
    FROM sales GROUP BY item_no
)
SELECT COUNT(*) AS items,
       SUM(CASE WHEN sizes > 1 THEN 1 ELSE 0 END)        AS items_multi_size,
       SUM(CASE WHEN packs > 1 THEN 1 ELSE 0 END)        AS items_multi_pack,
       SUM(CASE WHEN vendors > 1 THEN 1 ELSE 0 END)      AS items_multi_vendor,
       SUM(CASE WHEN descriptions > 1 THEN 1 ELSE 0 END) AS items_multi_description
FROM per_item
''').df().T
""")

md(r"""
**6f. Which weekdays do stores order on?** This decides what a "complete week" means at the edges of the data.
""")
code(r"""
con.execute('''
SELECT dayname(order_date) AS weekday, COUNT(*) AS lines
FROM sales GROUP BY 1, dayofweek(order_date) ORDER BY dayofweek(order_date)
''').df()
""")

md(r"""
**6g. Truncated decimals, and the repair.**
**What:** some rows have their decimals cut off: a bottle that costs stores $37.49 shows as 37, so 12 bottles show as
$449 instead of $449.88, and liters and gallons are cut to whole numbers too (9 instead of 9.00 is harmless, but
2 gallons instead of 2.378 is not). This block measures the problem by year, then repairs it:
- **Volume** is recomputed from the parts that are never truncated: liters = bottles × bottle ml ÷ 1000, 9-liter cases
  = liters ÷ 9, physical cases = bottles ÷ pack. The state's liters and gallons columns are not used.
- **Prices:** a row's price counts as truncated when it is a whole number and the same item, in the same month, has a
  usual price with cents whose whole-dollar part equals it. That row gets the usual price (the most common price with
  cents for that item and month). If that month has none, the row takes the nearest-dated clean price of the same
  item within 3 months either side, again only if its whole-dollar part matches (decision 32). Dollars are then
  bottles × repaired price.
- A whole-number price with no clean price to repair it keeps the **state's own line total**, not bottles × the
  truncated price: a truncated line total loses under $1 per line, a truncated unit price up to $1 per bottle.
- Rows with no per-bottle price at all (the state's files leave cost and retail blank before July 2025) keep the
  state's own dollar total. `dollars_source` says which rule each row used. Dollars at state cost are not used
  anywhere in the first release (decision 33).
- The raw columns are kept next to the repaired ones (`*_raw`) so the repair can always be audited.

**Why:** sales dollars are one of the two forecast targets, and cutting cents off every price biases dollars down by up
to a few percent on the affected rows; for small bottles the volume error is much bigger (0.297 gallons shown as 0).
Repairing from the same item's own price that month is the least invasive fix: it never invents a price the item
didn't carry.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE price_mode AS
WITH dec AS (   -- rows whose prices still have cents
    SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS month_start, state_bottle_retail, state_bottle_cost
    FROM sales
    WHERE order_date IS NOT NULL
      AND state_bottle_retail <> floor(state_bottle_retail)
),
r AS (
    SELECT item_no, month_start, state_bottle_retail AS p, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY item_no, month_start ORDER BY COUNT(*) DESC, state_bottle_retail DESC) AS rn
    FROM dec GROUP BY item_no, month_start, state_bottle_retail
),
c AS (
    SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS month_start, state_bottle_cost AS p, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY item_no, CAST(date_trunc('month', order_date) AS DATE)
                              ORDER BY COUNT(*) DESC, state_bottle_cost DESC) AS rn
    FROM sales
    WHERE order_date IS NOT NULL AND state_bottle_cost <> floor(state_bottle_cost)
    GROUP BY item_no, CAST(date_trunc('month', order_date) AS DATE), state_bottle_cost
)
SELECT COALESCE(r.item_no, c.item_no) AS item_no, COALESCE(r.month_start, c.month_start) AS month_start,
       r.p AS retail_mode, c.p AS cost_mode
FROM (SELECT * FROM r WHERE rn = 1) r
FULL OUTER JOIN (SELECT * FROM c WHERE rn = 1) c ON c.item_no = r.item_no AND c.month_start = r.month_start
''')

# decision 32: when the item-month has no matching cents price, use the nearest-dated clean row of the same item within
# 3 months either side whose whole-dollar part matches (ties: closer date, more rows that day, higher price)
con.execute('''
CREATE OR REPLACE TABLE price_near AS
WITH clean AS (
    SELECT item_no, order_date, state_bottle_retail AS p, COUNT(*) AS n
    FROM sales WHERE order_date IS NOT NULL AND state_bottle_retail <> floor(state_bottle_retail)
    GROUP BY 1, 2, 3
),
need AS (
    SELECT DISTINCT s.item_no, s.order_date, s.state_bottle_retail AS w
    FROM sales s
    LEFT JOIN price_mode pm ON pm.item_no = s.item_no AND pm.month_start = CAST(date_trunc('month', s.order_date) AS DATE)
    WHERE s.order_date IS NOT NULL AND s.state_bottle_retail = floor(s.state_bottle_retail)
      AND (pm.retail_mode IS NULL OR floor(pm.retail_mode) <> s.state_bottle_retail)
)
SELECT n.item_no, n.order_date, n.w, c.p AS retail_near
FROM need n JOIN clean c
  ON c.item_no = n.item_no AND floor(c.p) = n.w
 AND c.order_date BETWEEN CAST(n.order_date - INTERVAL 3 MONTH AS DATE) AND CAST(n.order_date + INTERVAL 3 MONTH AS DATE)
QUALIFY ROW_NUMBER() OVER (PARTITION BY n.item_no, n.order_date, n.w
                           ORDER BY abs(date_diff('day', c.order_date, n.order_date)), c.n DESC, c.p DESC) = 1
''')

con.execute('''
CREATE OR REPLACE TABLE sales AS
WITH x AS (
    SELECT s.*,
           CASE WHEN s.state_bottle_retail = floor(s.state_bottle_retail) AND floor(pm.retail_mode) = s.state_bottle_retail
                THEN pm.retail_mode
                WHEN s.state_bottle_retail = floor(s.state_bottle_retail) AND pn.retail_near IS NOT NULL
                THEN pn.retail_near
                ELSE s.state_bottle_retail END AS retail_fixed,
           CASE WHEN s.state_bottle_retail = floor(s.state_bottle_retail) AND floor(pm.retail_mode) = s.state_bottle_retail
                THEN 'same month'
                WHEN s.state_bottle_retail = floor(s.state_bottle_retail) AND pn.retail_near IS NOT NULL
                THEN 'nearest date' END AS retail_repair,
           CASE WHEN s.state_bottle_cost = floor(s.state_bottle_cost) AND floor(pm.cost_mode) = s.state_bottle_cost
                THEN pm.cost_mode ELSE s.state_bottle_cost END AS cost_fixed,
           (pm.retail_mode IS NOT NULL OR pn.retail_near IS NOT NULL) AS has_price_ref
    FROM sales s
    LEFT JOIN price_mode pm
      ON pm.item_no = s.item_no AND pm.month_start = CAST(date_trunc('month', s.order_date) AS DATE)
    LEFT JOIN price_near pn
      ON pn.item_no = s.item_no AND pn.order_date = s.order_date AND pn.w = s.state_bottle_retail
)
SELECT * EXCLUDE (state_bottle_cost, state_bottle_retail, sales_dollars, sales_liters, sales_gallons, retail_fixed, cost_fixed, retail_repair, sig),
       x.state_bottle_cost   AS state_bottle_cost_raw,
       x.state_bottle_retail AS state_bottle_retail_raw,
       x.sales_dollars       AS sales_dollars_raw,
       x.sales_liters        AS sales_liters_raw,
       x.sales_gallons       AS sales_gallons_raw,
       x.cost_fixed                     AS state_bottle_cost,
       x.retail_fixed                   AS state_bottle_retail,
       -- decision 32 (judge addendum 2): the state's line total is kept in every year. A line is repaired only when it
       -- shows the truncation signature: a whole-number total less than $1 below bottles x a clean cents price.
       CASE WHEN x.sig THEN x.sales_bottles * x.retail_fixed ELSE x.sales_dollars END AS sales_dollars,
       CASE WHEN x.sig AND x.retail_repair IS NULL THEN 'repaired total (price on row)'
            WHEN x.sig AND x.retail_repair = 'same month' THEN 'repaired total (same-month price)'
            WHEN x.sig THEN 'repaired total (nearest-date price)'
            WHEN x.sales_dollars = floor(x.sales_dollars) THEN 'state total (whole number)'
            ELSE 'state total' END AS dollars_source,
       x.sales_bottles * x.bottle_volume_ml / 1000.0 AS sales_liters,
       x.sales_bottles * x.bottle_volume_ml / 1000.0 / 9.0 AS cases_9l,
       x.sales_bottles * 1.0 / NULLIF(x.pack, 0) AS physical_cases,
       (x.retail_fixed <> x.state_bottle_retail OR x.cost_fixed <> x.state_bottle_cost) AS price_repaired,
       ABS(x.sales_dollars - x.sales_bottles * x.state_bottle_retail) > 0.01 AS dollars_mismatch_raw
FROM (SELECT *, COALESCE(sales_bottles > 0 AND retail_fixed <> floor(retail_fixed)
                        AND sales_dollars = floor(sales_dollars)
                        AND sales_bottles * retail_fixed - sales_dollars > 0.005   -- above half a cent, so float noise on exact totals is not a repair
                        AND sales_bottles * retail_fixed - sales_dollars < 1, FALSE) AS sig FROM x) x
''')

trunc = con.execute('''
SELECT year(order_date) AS year,
       COUNT(*) AS lines,
       SUM(CASE WHEN state_bottle_retail_raw = floor(state_bottle_retail_raw) THEN 1 ELSE 0 END) AS whole_number_retail,
       SUM(CASE WHEN price_repaired THEN 1 ELSE 0 END)           AS lines_repaired,
       SUM(CASE WHEN dollars_mismatch_raw THEN 1 ELSE 0 END)     AS raw_dollars_mismatch,
       SUM(CASE WHEN state_bottle_retail_raw = floor(state_bottle_retail_raw) AND NOT has_price_ref THEN sales_dollars_raw ELSE 0 END) AS dollars_whole_price_no_ref,
       SUM(CASE WHEN sales_liters_raw <> floor(sales_liters_raw) THEN 0 ELSE 1 END) AS whole_number_liters,
       SUM(sales_dollars_raw)                                    AS dollars_raw,
       SUM(sales_dollars)                                        AS dollars_repaired
FROM sales WHERE order_date IS NOT NULL
GROUP BY 1 ORDER BY 1
''').df()
trunc["pct_lines_repaired"] = 100 * trunc.lines_repaired / trunc.lines
trunc["pct_raw_dollars_mismatch"] = 100 * trunc.raw_dollars_mismatch / trunc.lines
trunc["pct_dollars_unrepairable"] = 100 * trunc.dollars_whole_price_no_ref / trunc.dollars_raw
trunc["pct_dollar_change"] = 100 * (trunc.dollars_repaired / trunc.dollars_raw - 1)
trunc.to_csv(OUT / "truncation_by_year.csv", index=False)
display(trunc.round(3))

con.execute('''
SELECT SUM(CASE WHEN bottle_volume_ml IS NULL OR bottle_volume_ml <= 0 THEN 1 ELSE 0 END) AS bad_volume_lines,
       SUM(CASE WHEN pack IS NULL OR pack <= 0 THEN 1 ELSE 0 END)                         AS bad_pack_lines,
       SUM(CASE WHEN state_bottle_retail_raw = floor(state_bottle_retail_raw) AND NOT has_price_ref THEN 1 ELSE 0 END) AS whole_price_no_cents_reference,
       (SELECT COUNT(*) FROM (SELECT item_no FROM sales GROUP BY item_no HAVING COUNT(DISTINCT bottle_volume_ml) > 1)) AS items_with_size_change,
       (SELECT COUNT(*) FROM (SELECT item_no FROM sales GROUP BY item_no HAVING COUNT(DISTINCT pack) > 1))             AS items_with_pack_change
FROM sales
''').df().T
""")

md(r"""
## 6f. Unit breaks in bottles (decisions 60 and 62, judge's Addendum 8; protocol 1.10 section 1) and zero lines (decision 61)
**What:** some items change what one recorded "bottle" is (a case of 10 single minis becomes a case of one 10-pack)
and the state records a new `pack` (bottles per case) at the same time. A **unit break** is a change in the item's
recorded pack (the most common pack of the month) of 1.8x or more, either way, where dollars per bottle moved the
opposite way by about the same amount: (median line price after / before) / (old pack / new pack) within **0.8 to 1.25**
confirms it by rule. Between that and 0.67 to 1.5 it is listed for a hand read and gets no automatic factor. Outside
0.67 to 1.5 it is an ordinary change of case size and is left alone. Medians are over lines carrying the old pack in up
to 3 months with orders before the change and lines carrying the new pack in up to 3 months from it, counting only
months within 12 calendar months of the break (decision 62); one month is enough, none on a side means no break.
**Restatement, line by line:** a line's factor is the product of the confirmed ratios (new pack / old pack) of every
confirmed break after it. Inside a break's windows a line is before or after it by its own price (nearer in log to the
before or the after median), then by its recorded pack, then by month: the state relabels the pack on every line at the
switch while some lines still carry the old unit's price (decision 62). An unconfirmed pack change contributes 1.
**Continuity test** on every restated item: at each confirmed break, restated units after / before (median month, same
windows) within 0.5 to 2 and dollars per restated unit within 0.67 to 1.5. An item that fails is not restated; its
series starts at its last confirmed break (rows before it become `item~preYYYYMM`) and it is reported.
**The frozen action table `stage1/unit_breaks.csv` decides (judge's Addendum 9, ruling 01b amendment):** the rule above
only proposes breaks; every row of the table was read by hand and carries an action: `restate` (factor = new pack /
old pack, or the ruled factor; still subject to the continuity test), `cut` (series starts at the break), or
`leave_alone`. A break the rule confirms that is missing from the table is reported and not applied. The rule's own
proposals go to `unit_pack_changes_all.csv`, what was applied to `unit_breaks_applied.csv`. **Price steps without pack evidence** (1.8x or more between 3-month medians, dollars smooth)
are listed in `unexplained_steps.csv`, not restated. **Zero lines (decision 61):** lines with bottles but $0, and
lines with dollars but 0 bottles, are flagged and kept; they stay out of every price median. Dollars never change.
""")
code(r"""
UB_PACK_STEP = 1.8                                   # old pack / new pack, or its inverse
UB_CONFIRM, UB_HAND = (0.8, 1.25), (0.67, 1.5)       # price ratio / pack ratio: confirmed; hand read (Addendum 8)
UB_CONT_UNITS, UB_CONT_PRICE = (0.5, 2.0), (0.67, 1.5)
UB_CAP_MONTHS = 12                                   # decision 62: median months within 12 calendar months of the break
UB_STEP, UB_SMOOTH = 1.8, (0.67, 1.5)                # unexplained price steps (listed only)
tab = pd.read_csv(OUT / "unit_breaks.csv", dtype={"item_no": str, "month": str})      # frozen, read by hand
TABLE = {(r.item_no, r.month): (r.action, float(r.factor) if pd.notna(r.factor) else np.nan) for r in tab.itertuples()}
assert set(a for a, _ in TABLE.values()) <= {"restate", "cut", "leave_alone"}

# decision 61: flags (kept, out of price medians)
con.execute('''CREATE OR REPLACE TABLE sales AS SELECT *,
    COALESCE(sales_bottles > 0 AND sales_dollars = 0, FALSE)                             AS zero_dollar_line,
    COALESCE(COALESCE(sales_bottles, 0) = 0 AND COALESCE(sales_dollars, 0) <> 0, FALSE) AS zero_bottle_line
FROM sales''')
zl = con.execute('''SELECT year(order_date) AS year,
       SUM(CASE WHEN zero_dollar_line THEN 1 ELSE 0 END) AS zero_dollar_lines,
       SUM(CASE WHEN zero_dollar_line THEN sales_bottles ELSE 0 END) AS zero_dollar_bottles,
       SUM(CASE WHEN zero_bottle_line THEN 1 ELSE 0 END) AS zero_bottle_lines,
       ROUND(SUM(CASE WHEN zero_bottle_line THEN sales_dollars ELSE 0 END), 2) AS zero_bottle_dollars
FROM sales WHERE order_date IS NOT NULL GROUP BY 1 ORDER BY 1''').df()
zl.to_csv(OUT / "evidence_zero_lines_by_year.csv", index=False)
print(f"zero-dollar lines (bottles > 0, $0): {int(zl.zero_dollar_lines.sum()):,} ({int(zl.zero_dollar_bottles.sum()):,} bottles); "
      f"zero-bottle lines with dollars: {int(zl.zero_bottle_lines.sum()):,} (${zl.zero_bottle_dollars.sum():,.2f})")

ln = con.execute('''
WITH ip AS (SELECT item_no FROM sales WHERE sales_bottles > 0 AND order_date IS NOT NULL AND pack > 0
            GROUP BY 1 HAVING MAX(pack) >= 1.8 * MIN(pack))
SELECT s.rowid AS rid, s.item_no, CAST(date_trunc('month', s.order_date) AS DATE) AS m, s.pack, s.sales_bottles AS b,
       s.sales_dollars AS usd, s.zero_dollar_line AS z
FROM sales s JOIN ip USING (item_no) WHERE s.sales_bottles > 0 AND s.order_date IS NOT NULL''').df()
ln["m"] = pd.to_datetime(ln.m)
ln["pr"] = np.where(ln.z | ln.usd.isna(), np.nan, ln.usd / ln.b)

def ub_find(g):
    months = np.sort(g.m.unique()); mi = {x: i for i, x in enumerate(months)}
    dom = (g[g.pack > 0].groupby(["m", "pack"]).agg(n=("b", "size"), bt=("b", "sum")).reset_index()
             .sort_values(["m", "n", "bt", "pack"], ascending=[True, False, False, True]).drop_duplicates("m"))
    seq = list(zip(dom.m, dom.pack))
    rows = []
    for (m0, A), (m1, B) in zip(seq[:-1], seq[1:]):
        if A == B:
            continue
        q = A / B
        if 1 / UB_PACK_STEP < q < UB_PACK_STEP:
            continue
        j = mi[m1]; m1 = pd.Timestamp(m1)
        wb = [x for x in months[max(0, j - 3):j] if x >= m1 - pd.DateOffset(months=UB_CAP_MONTHS)]
        wa = [x for x in months[j:j + 3] if x <= m1 + pd.DateOffset(months=UB_CAP_MONTHS)]
        pb = g.pr[g.m.isin(wb) & (g.pack == A)].dropna(); pa = g.pr[g.m.isin(wa) & (g.pack == B)].dropna()
        key = (g.item_no.iat[0], m1.strftime("%Y-%m"))
        action, f = TABLE.get(key, (None, np.nan))
        if action in ("restate", "cut") and (not len(pb) or not len(pa)):
            # a hand-read entry with no rule window: windows without the calendar cap; continuity still applies
            wb, wa = list(months[max(0, j - 3):j]), list(months[j:j + 3])
            pb = g.pr[g.m.isin(wb) & (g.pack == A)].dropna(); pa = g.pr[g.m.isin(wa) & (g.pack == B)].dropna()
        base = dict(item_no=key[0], month=m1, pack_old=A, pack_new=B, pack_ratio=q, wb=wb, wa=wa, action=action,
                    factor=f if action in ("restate", "cut") else np.nan)
        if not len(pb) or not len(pa):
            rows.append(dict(base, P0=np.nan, P1=np.nan, price_ratio=np.nan, price_over_pack=np.nan, status="no_prices_in_cap"))
            continue
        P0, P1 = float(np.median(pb)), float(np.median(pa)); s = (P1 / P0) / q
        st = ("confirmed" if UB_CONFIRM[0] <= s <= UB_CONFIRM[1] else "hand_read" if UB_HAND[0] <= s <= UB_HAND[1] else "case_size")
        rows.append(dict(base, P0=P0, P1=P1, price_ratio=P1 / P0, price_over_pack=s, status=st))
    return rows

def ub_before(g, x):
    # 1 = line is before break x (old unit). Inside the windows: own price, then recorded pack, then month.
    inw = g.m.isin(list(x["wb"]) + list(x["wa"])).to_numpy()
    pk = g.pack.to_numpy(); pr = g.pr.to_numpy(); bym = (g.m < x["month"]).to_numpy()
    by_pack = np.where(pk == x["pack_old"], True, np.where(pk == x["pack_new"], False, bym))
    with np.errstate(all="ignore"):
        near0 = np.abs(np.log(pr / x["P0"])) < np.abs(np.log(pr / x["P1"]))
    inside = np.where(np.isfinite(pr), near0, by_pack)
    return np.where(inw, inside, bym)

ub_rows, adj, cont = [], [], []
for it, g in ln.groupby("item_no", sort=False):
    rows = ub_find(g)
    if not rows:
        continue
    ub_rows += rows
    act = [x for x in rows if x["action"] in ("restate", "cut")]       # applied only through the frozen table
    if not act:
        continue
    forced_cut = any(x["action"] == "cut" for x in act)
    mult = np.ones(len(g)); bef = []
    for x in act:
        bef.append(ub_before(g, x))
        mult = np.where(bef[-1], mult * x["factor"], mult)
    rb = g.b.to_numpy(float) * mult
    nz = (~g.z & g.usd.notna()).to_numpy(); usd = g.usd.to_numpy(float)
    ok_item = True
    for x in act:
        wb, wa = g.m.isin(x["wb"]).to_numpy(), g.m.isin(x["wa"]).to_numpy()
        mb = pd.Series(rb[wb]).groupby(g.m.to_numpy()[wb]).sum().median()
        ma = pd.Series(rb[wa]).groupby(g.m.to_numpy()[wa]).sum().median()
        pb_ = usd[wb & nz].sum() / rb[wb & nz].sum() if (wb & nz).any() else np.nan
        pa_ = usd[wa & nz].sum() / rb[wa & nz].sum() if (wa & nz).any() else np.nan
        cu, cp = ma / mb, pa_ / pb_
        good = bool(UB_CONT_UNITS[0] <= cu <= UB_CONT_UNITS[1] and UB_CONT_PRICE[0] <= cp <= UB_CONT_PRICE[1])
        cont.append(dict(item_no=it, month=x["month"], units_after_over_before=cu, price_after_over_before=cp, continuity_ok=good))
        ok_item &= good
    if ok_item and not forced_cut:
        keep = mult != 1
        adj.append(pd.DataFrame({"rid": g.rid.to_numpy()[keep], "mult": mult[keep], "new_item": it}))
    else:
        pre = bef[-1]
        adj.append(pd.DataFrame({"rid": g.rid.to_numpy()[pre], "mult": 1.0, "new_item": f"{it}~pre{act[-1]['month']:%Y%m}"}))

ub = pd.DataFrame(ub_rows, columns=["item_no", "month", "pack_old", "pack_new", "pack_ratio", "P0", "P1", "price_ratio",
                                    "price_over_pack", "status", "action", "factor", "wb", "wa"])
ub["months_before"] = ub.wb.map(len); ub["months_after"] = ub.wa.map(len); ub = ub.drop(columns=["wb", "wa"])
ct = pd.DataFrame(cont, columns=["item_no", "month", "units_after_over_before", "price_after_over_before", "continuity_ok"])
ub = ub.merge(ct, on=["item_no", "month"], how="left")
cut_items = set(ct.item_no[~ct.continuity_ok.astype(bool)]) | set(ub.item_no[ub.action == "cut"])
applied_rows = ub.action.isin(["restate", "cut"])
ub["outcome"] = np.select([applied_rows & ub.item_no.isin(cut_items), applied_rows], ["cut_at_last_break", "restated"], "not_applied")
not_in_table = ub[(ub.status == "confirmed") & ub.action.isna()]
table_unmatched = set(TABLE) - set(zip(ub.item_no, ub.month.dt.strftime("%Y-%m")))
restate_cut = ub[(ub.action == "restate") & (ub.outcome == "cut_at_last_break")]
adj = pd.concat(adj, ignore_index=True) if adj else pd.DataFrame({"rid": pd.Series([], dtype="int64"),
                                                                     "mult": pd.Series([], dtype=float),
                                                                     "new_item": pd.Series([], dtype=str)})
# date cuts (ruling 01d A3): a table `cut` row that is not a pack change cuts the item's history at that month; its earlier
# lines become item~preYYYYMM, are never restated, and override any factor from a later break
date_cuts = {k: v for k, v in TABLE.items() if k in table_unmatched and v[0] == "cut"}
dc = []
for (it, mo), _ in date_cuts.items():
    r = con.execute("SELECT rowid AS rid FROM sales WHERE item_no = ? AND order_date < ?",
                    [it, pd.Timestamp(mo + "-01").date()]).df()
    dc.append(r.assign(mult=1.0, new_item=f"{it}~pre{mo.replace('-', '')}"))
if dc:
    dc = pd.concat(dc, ignore_index=True)
    adj = pd.concat([adj[~adj.rid.isin(dc.rid)], dc], ignore_index=True)
pd.DataFrame([dict(item_no=k[0], month=k[1], lines=int((dc.new_item == f"{k[0]}~pre{k[1].replace('-', '')}").sum()) if len(date_cuts) else 0)
              for k in date_cuts]).to_csv(OUT / "unit_date_cuts.csv", index=False)
table_unmatched = table_unmatched - set(date_cuts)
con.register("ub_adj", adj)
con.execute('''
CREATE OR REPLACE TABLE sales AS
SELECT s.* REPLACE (COALESCE(a.new_item, s.item_no) AS item_no,
                    CAST(s.sales_bottles AS DOUBLE) * COALESCE(a.mult, 1.0) AS sales_bottles),
       s.sales_bottles AS sales_bottles_recorded
FROM sales s LEFT JOIN ub_adj a ON a.rid = s.rowid''')
con.unregister("ub_adj")
t12d = con.execute('''SELECT regexp_replace(item_no, '~pre.*', '') AS item_no, SUM(sales_dollars) AS usd_t12 FROM sales
                      WHERE sales_bottles > 0 AND order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH
                      GROUP BY 1''').df()
ub = ub.merge(t12d, on="item_no", how="left").fillna({"usd_t12": 0}).sort_values(["usd_t12", "month"], ascending=[False, True])
ub["in_2025_26"] = ub.month >= pd.Timestamp("2025-01-01")
ub.to_csv(OUT / "unit_pack_changes_all.csv", index=False)
brk = ub[ub.action.isin(["restate", "cut"])]
brk.to_csv(OUT / "unit_breaks_applied.csv", index=False)
ub[ub.status == "hand_read"].to_csv(OUT / "unit_breaks_hand_read.csv", index=False)
ub[~ub.action.isin(["restate", "cut"])].to_csv(OUT / "pack_changes_left_alone.csv", index=False)
brk[brk.outcome == "cut_at_last_break"].to_csv(OUT / "unit_breaks_continuity_fail.csv", index=False)
(OUT / "unit_breaks_size_changes.csv").unlink(missing_ok=True)      # decision 50 output, no longer made
print(f"frozen table: {len(TABLE)} rows; confirmed by the rule but not in the table: {len(not_in_table)} "
      f"{not_in_table.item_no.tolist()}; date cuts: {sorted(date_cuts)}; other table rows with no pack change: {sorted(table_unmatched)}; "
      f"table 'restate' rows cut by the continuity test: {restate_cut.item_no.tolist()}")

# price steps of 1.8x or more with dollars smooth, on restated units: listed, never restated
um = con.execute('''SELECT regexp_replace(item_no, '~pre.*', '') AS item_no, CAST(date_trunc('month', order_date) AS DATE) AS m,
       SUM(sales_bottles) AS b, SUM(CASE WHEN NOT zero_dollar_line THEN sales_dollars END) AS usd,
       SUM(CASE WHEN NOT zero_dollar_line THEN sales_bottles END) AS bp, MIN(pack) AS pack_min, MAX(pack) AS pack_max
FROM sales WHERE sales_bottles > 0 AND order_date IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2''').df()
um["p"] = um.usd / um.bp
rng = um.groupby("item_no").p.agg(lambda v: np.nanmax(v) / np.nanmin(v) if np.isfinite(v).any() and np.nanmin(v) > 0 else 1.0)
steps = []
for it, g in um[um.item_no.isin(rng[rng >= UB_STEP].index)].groupby("item_no", sort=False):
    p, bt, mm = g.p.to_numpy(float), g.b.to_numpy(float), pd.to_datetime(g.m).to_numpy()
    pk0, pk1 = g.pack_min.to_numpy(float), g.pack_max.to_numpy(float)
    hits = []
    for i in range(1, len(g)):
        xb, xa = p[max(0, i - 3):i], p[i:i + 3]
        xb, xa = xb[np.isfinite(xb)], xa[np.isfinite(xa)]
        if not len(xb) or not len(xa):
            continue
        pb, pa = np.median(xb), np.median(xa)
        if not (pb > 0 and pa > 0):
            continue
        r = pa / pb
        if 1 / UB_STEP < r < UB_STEP:
            continue
        dr = r * np.median(bt[i:i + 3]) / np.median(bt[max(0, i - 3):i])
        if UB_SMOOTH[0] <= dr <= UB_SMOOTH[1]:
            hits.append((i, r, pb, pa, dr))
    run = []
    for h in hits + [None]:
        if h is not None and run and h[0] == run[-1][0] + 1:
            run.append(h); continue
        if run:
            i, r, pb, pa, dr = max(run, key=lambda z: abs(np.log(z[1])))
            w = slice(max(0, i - 3), i + 3)
            steps.append(dict(item_no=it, month=pd.Timestamp(mm[i]), P0=pb, P1=pa, price_ratio=r, dollars_ratio=dr,
                              pack_change_nearby=bool(pd.Series(pk1[w]).max() != pd.Series(pk0[w]).min())))
        run = [h] if h is not None else []
us = pd.DataFrame(steps, columns=["item_no", "month", "P0", "P1", "price_ratio", "dollars_ratio", "pack_change_nearby"])
us = us.merge(t12d, on="item_no", how="left").fillna({"usd_t12": 0}).sort_values("usd_t12", ascending=False)
us.to_csv(OUT / "unexplained_steps.csv", index=False)

n_t12 = brk[brk.usd_t12 > 0]
vc = ub.status.value_counts()
print("pack changes of 1.8x+ (rule): " + ", ".join(f"{k} {v}" for k, v in vc.items()) + "; table actions: "
      + ", ".join(f"{k} {v}" for k, v in ub.action.value_counts().items()))
print(f"breaks applied: {len(brk)} on {brk.item_no.nunique()} items; restated {int((brk.outcome == 'restated').sum())}, "
      f"cut {int((brk.outcome == 'cut_at_last_break').sum())}; lines adjusted: {len(adj):,}; "
      f"breaks inside 2025-26: {int(brk.in_2025_26.sum())}")
print(f"breaks on items with trailing-12 sales (hand check): {len(n_t12)} on {n_t12.item_no.nunique()} items "
      f"(${n_t12.drop_duplicates('item_no').usd_t12.sum():,.0f}); unexplained price steps listed: {len(us)} "
      f"({int((us.usd_t12 > 50000).sum())} above $50,000 t12)")
""")

md(r"""
## 7. The dialect block (the only lines that differ between DuckDB and BigQuery)
**What:** small SQL pieces written once for DuckDB and once for BigQuery: the start of the week and month,
adding days to a date, the table name, and a list of weekly dates. Every query below is built from these pieces, and the BigQuery
version of each query is saved to `stage1/sql_bigquery/` so it can run there later.
**Why:** keeping the differences in one place is what makes "same SQL in both" honest instead of a claim.
Weeks start on **Monday** (ISO weeks) in both.
""")
code(r"""
DIALECTS = {
    "duckdb": {
        "week": lambda c: f"CAST(date_trunc('week', {c}) AS DATE)",
        "add_days": lambda c, n: f"CAST(DATE_ADD({c}, INTERVAL ({n}) DAY) AS DATE)",
        "week_list": lambda a, b: f"unnest(generate_series(CAST({a} AS TIMESTAMP), CAST({b} AS TIMESTAMP), INTERVAL 7 DAY))",
        "table": lambda t: t,
        "month": lambda c: f"CAST(date_trunc('month', {c}) AS DATE)",
        "month_list": lambda a, b: f"unnest(generate_series(CAST({a} AS TIMESTAMP), CAST({b} AS TIMESTAMP), INTERVAL 1 MONTH))",
    },
    "bigquery": {
        "week": lambda c: f"DATE_TRUNC({c}, ISOWEEK)",
        "add_days": lambda c, n: f"DATE_ADD({c}, INTERVAL ({n}) DAY)",
        "week_list": lambda a, b: f"UNNEST(GENERATE_DATE_ARRAY({a}, {b}, INTERVAL 7 DAY))",
        "table": lambda t: f"`iowa_liquor.{t}`",
        "month": lambda c: f"DATE_TRUNC({c}, MONTH)",
        "month_list": lambda a, b: f"UNNEST(GENERATE_DATE_ARRAY({a}, {b}, INTERVAL 1 MONTH))",
    },
}
SQL_BQ = OUT / "sql_bigquery"; SQL_BQ.mkdir(exist_ok=True)

def run(name, build):
    # build(d) returns the SQL text for dialect d; run it in DuckDB, save the BigQuery text
    (SQL_BQ / f"{name}.sql").write_text(build(DIALECTS["bigquery"]))
    con.execute(f"CREATE OR REPLACE TABLE {name} AS " + build(DIALECTS["duckdb"]))
    return con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
""")

md(r"""
## 8. Complete weeks only (weekly side table)
**What:** finds the first and last **complete** Monday-to-Sunday weeks in the file.
**Why:** 2026 starts on a Thursday holiday and the file ends partway through a week. A part-week looks like a
demand drop, which would bias every forecast and class downward at the edges, so part-weeks are dropped.
""")
code(r"""
def q_weeks(d):
    w, T, add = d["week"], d["table"], d["add_days"]
    return f'''
    SELECT
        CASE WHEN {w('MIN(order_date)')} = MIN(order_date)
             THEN MIN(order_date) ELSE {add(w('MIN(order_date)'), 7)} END AS first_week,
        CASE WHEN {add(w('MAX(order_date)'), 6)} <= MAX(order_date)
             THEN {w('MAX(order_date)')} ELSE {add(w('MAX(order_date)'), -7)} END AS last_week
    FROM {T('sales')}
    '''
run("week_bounds", q_weeks)
con.execute("SELECT *, date_diff('day', first_week, last_week) / 7 + 1 AS n_weeks FROM week_bounds").df()
""")

md(r"""
## 9. Weekly demand per product, zeros filled (side table for a later weekly view)
**What:** sums bottles ordered per item per week, then lays every item over a full list of weeks and writes 0
where an item had no orders.
**Why:** a plain GROUP BY only returns weeks *with* orders, so a slow item would look like it sells every week.
Intermittent-demand methods (Croston, SBA, TSB) work on the gaps, so the zeros have to be real rows.
Each item's history starts at its **first week with demand**, so an item launched in June isn't given
five months of false zeros. Spend uses `sales_dollars` (what stores paid the state), because state cost is blank
before July 2025 and dollars at cost are out of the first release (decision 33).
""")
code(r"""
def q_weekly(d):
    w, T, wl = d["week"], d["table"], d["week_list"]
    return f'''
    WITH lines AS (
        SELECT item_no, {w('order_date')} AS week_start,
               sales_bottles, sales_dollars AS dollars
        FROM {T('sales')}
        WHERE sales_bottles > 0 AND order_date IS NOT NULL
    ),
    item_week AS (
        SELECT item_no, week_start,
               SUM(sales_bottles) AS bottles, SUM(dollars) AS dollars, COUNT(*) AS order_lines
        FROM lines, {T('week_bounds')} b
        WHERE week_start BETWEEN b.first_week AND b.last_week
        GROUP BY item_no, week_start
    ),
    item_span AS (
        SELECT item_no, MIN(week_start) AS first_demand_week FROM item_week GROUP BY item_no
    ),
    spine AS (
        SELECT s.item_no, CAST(wk AS DATE) AS week_start
        FROM item_span s, {T('week_bounds')} b, {wl('s.first_demand_week', 'b.last_week')} AS t(wk)
    )
    SELECT sp.item_no, sp.week_start,
           COALESCE(iw.bottles, 0)      AS bottles,
           COALESCE(iw.dollars, 0)      AS dollars,
           COALESCE(iw.order_lines, 0)  AS order_lines
    FROM spine sp
    LEFT JOIN item_week iw ON iw.item_no = sp.item_no AND iw.week_start = sp.week_start
    '''
n = run("weekly_demand", q_weekly)
print(n, "item-weeks")
con.execute('''
SELECT COUNT(DISTINCT item_no) AS items, COUNT(*) AS item_weeks,
       AVG(CASE WHEN bottles = 0 THEN 1.0 ELSE 0.0 END) AS zero_week_share
FROM weekly_demand''').df()
""")

md(r"""
**Check:** the weekly table must hold exactly the bottles from the order lines inside the complete weeks,
and every item must have one row per week from its first demand week to the last week (no gaps, no duplicates).
""")
code(r"""
con.execute(f'''
SELECT
  (SELECT SUM(bottles) FROM weekly_demand) AS weekly_total,
  (SELECT SUM(sales_bottles) FROM sales, week_bounds b
     WHERE sales_bottles > 0 AND {DIALECTS["duckdb"]["week"]("order_date")} BETWEEN b.first_week AND b.last_week) AS lines_total,
  (SELECT COUNT(*) FROM (SELECT item_no, week_start FROM weekly_demand GROUP BY 1,2 HAVING COUNT(*) > 1)) AS duplicate_rows,
  (SELECT COUNT(*) FROM (
      SELECT item_no FROM weekly_demand GROUP BY item_no
      HAVING COUNT(*) <> date_diff('day', MIN(week_start), MAX(week_start)) / 7 + 1)) AS items_with_gaps
''').df().T
""")

md(r"""
## 9b. The order-day calendar
**What:** builds a calendar of statewide order days: weekdays, less Iowa state holidays (New Year's Day, Martin Luther
King Jr. Day, Memorial Day, Independence Day, Labor Day, Veterans Day, Thanksgiving and the day after, Christmas; a
holiday on a Saturday is observed the Friday before and on a Sunday the Monday after). Then it checks that calendar
against the days the data actually has orders.
**Why:** the forecast target is bottles per order day, and a future month has no data, so its order days must come
from a calendar known in advance, never from the orders themselves. The data is used once, here, to show the calendar
is right: how many calendar days had no orders, and how many order days fall outside the calendar.
""")
code(r"""
import datetime as dt
import numpy as np
def nth_weekday(y, m, wd, n):           # n-th weekday (Mon=0) of a month; n=-1 for the last one
    if n > 0:
        d = dt.date(y, m, 1); d += dt.timedelta((wd - d.weekday()) % 7); return d + dt.timedelta(7 * (n - 1))
    d = dt.date(y, m + 1, 1) - dt.timedelta(1) if m < 12 else dt.date(y, 12, 31)
    return d - dt.timedelta((d.weekday() - wd) % 7)
def observed(d):
    return d - dt.timedelta(1) if d.weekday() == 5 else d + dt.timedelta(1) if d.weekday() == 6 else d
def iowa_holidays(y):
    thanks = nth_weekday(y, 11, 3, 4)
    return {observed(dt.date(y, 1, 1)), nth_weekday(y, 1, 0, 3), nth_weekday(y, 5, 0, -1), observed(dt.date(y, 7, 4)),
            nth_weekday(y, 9, 0, 1), observed(dt.date(y, 11, 11)), thanks, thanks + dt.timedelta(1),
            observed(dt.date(y, 12, 25))}
HOL = set().union(*[iowa_holidays(y) for y in range(2011, 2028)])
def iowa_holidays_named(y):
    thanks = nth_weekday(y, 11, 3, 4)
    return {observed(dt.date(y, 1, 1)): "New Year's Day", nth_weekday(y, 1, 0, 3): "Martin Luther King Jr. Day",
            nth_weekday(y, 5, 0, -1): "Memorial Day", observed(dt.date(y, 7, 4)): "Independence Day",
            nth_weekday(y, 9, 0, 1): "Labor Day", observed(dt.date(y, 11, 11)): "Veterans Day",
            thanks: "Thanksgiving", thanks + dt.timedelta(1): "Day after Thanksgiving",
            observed(dt.date(y, 12, 25)): "Christmas"}
days = pd.date_range("2012-01-01", "2026-12-31", freq="D")
cal = pd.DataFrame({"day": days.date})
cal["order_day"] = [(d.weekday() < 5) and (d not in HOL) for d in cal.day]
con.execute("CREATE OR REPLACE TABLE calendar AS SELECT CAST(day AS DATE) AS day, order_day FROM cal")

check = con.execute('''
WITH d AS (SELECT DISTINCT order_date AS day FROM sales WHERE order_date IS NOT NULL)
SELECT year(c.day) AS year,
       SUM(CASE WHEN c.order_day THEN 1 ELSE 0 END)                                   AS calendar_order_days,
       SUM(CASE WHEN d.day IS NOT NULL THEN 1 ELSE 0 END)                              AS days_with_orders,
       SUM(CASE WHEN c.order_day AND d.day IS NULL THEN 1 ELSE 0 END)                  AS calendar_days_without_orders,
       SUM(CASE WHEN NOT c.order_day AND d.day IS NOT NULL THEN 1 ELSE 0 END)          AS order_days_off_calendar
FROM calendar c LEFT JOIN d ON d.day = c.day
WHERE c.day <= (SELECT MAX(order_date) FROM sales)
GROUP BY 1 ORDER BY 1''').df()
display(check)
print("days with orders that the calendar calls a non-order day (first 30):")
display(con.execute('''
SELECT d.day, dayname(d.day) AS weekday, COUNT(*) AS lines
FROM (SELECT order_date AS day FROM sales) d JOIN calendar c USING (day)
WHERE NOT c.order_day GROUP BY 1, 2 ORDER BY 1 LIMIT 30''').df())
print("calendar order days with no orders (first 30):")
display(con.execute('''
SELECT c.day, dayname(c.day) AS weekday FROM calendar c
WHERE c.order_day AND c.day <= (SELECT MAX(order_date) FROM sales)
  AND c.day NOT IN (SELECT DISTINCT order_date FROM sales WHERE order_date IS NOT NULL)
ORDER BY 1 LIMIT 30''').df())
""")

md(r"""
## 9c. Is October 2026 complete?
**What:** three tests on the last month in the file, run before any forecast is scored.
1. Friday's share of 2026 order lines: if Fridays carry real volume, a month missing its last Friday is short.
2. How often, in the past, a month's last calendar order day had no orders at all (if that never happens, a missing
   last day is a sign of a cut-off, not a quiet day).
3. October 2026 bottles per order day against September 2026 and October 2025.

**Rule (tightened):** the last month is complete only if its last order date equals its last calendar order day.
There is no "gap no bigger than usual" escape: that branch could pass a month that lost its last day.
**Why:** if October is short and treated as complete, it looks like a demand drop, and both the models and the test
scores would read it as one.
""")
code(r"""
t1 = con.execute('''
SELECT ROUND(100.0 * SUM(CASE WHEN isodow(order_date) = 5 THEN 1 ELSE 0 END) / COUNT(*), 1) AS friday_pct_of_lines_2026,
       ROUND(100.0 * SUM(CASE WHEN isodow(order_date) = 5 THEN sales_bottles ELSE 0 END) / SUM(sales_bottles), 1) AS friday_pct_of_bottles_2026
FROM sales WHERE year(order_date) = 2026 AND sales_bottles > 0''').df()
t2 = con.execute('''
WITH last_cal AS (
    SELECT CAST(date_trunc('month', day) AS DATE) AS month_start, MAX(day) AS last_order_day
    FROM calendar WHERE order_day GROUP BY 1
),
has AS (SELECT DISTINCT order_date AS day FROM sales)
SELECT COUNT(*) AS past_months,
       SUM(CASE WHEN h.day IS NULL THEN 1 ELSE 0 END) AS months_whose_last_order_day_was_empty
FROM last_cal l LEFT JOIN has h ON h.day = l.last_order_day
WHERE l.month_start < (SELECT CAST(date_trunc('month', MAX(order_date)) AS DATE) FROM sales)
  AND l.month_start >= DATE '2012-01-01' ''').df()
t3 = con.execute('''
WITH od AS (SELECT CAST(date_trunc('month', day) AS DATE) AS m, COUNT(*) AS cal_days FROM calendar WHERE order_day GROUP BY 1),
obs AS (SELECT CAST(date_trunc('month', order_date) AS DATE) AS m, COUNT(DISTINCT order_date) AS days_with_orders,
               SUM(CASE WHEN sales_bottles > 0 THEN sales_bottles ELSE 0 END) AS bottles, MAX(order_date) AS last_order
        FROM sales GROUP BY 1)
SELECT obs.m AS month, od.cal_days, obs.days_with_orders, obs.last_order, obs.bottles,
       ROUND(obs.bottles / obs.days_with_orders) AS bottles_per_observed_order_day
FROM obs JOIN od USING (m)
WHERE obs.m IN (DATE '2025-10-01', DATE '2026-09-01', DATE '2026-10-01') ORDER BY 1''').df()
display(t1); display(t2); display(t3)

last_m = con.execute("SELECT CAST(date_trunc('month', MAX(order_date)) AS DATE), MAX(order_date) FROM sales").fetchone()
last_cal_day = con.execute("SELECT MAX(day) FROM calendar WHERE order_day AND CAST(date_trunc('month', day) AS DATE) = ?",
                           [last_m[0]]).fetchone()[0]
LAST_MONTH_COMPLETE = last_m[1] >= last_cal_day
LAST_COMPLETE_MONTH = pd.Timestamp(last_m[0]) if LAST_MONTH_COMPLETE else pd.Timestamp(last_m[0]) - pd.offsets.MonthBegin(1)
print(f"last month {pd.Timestamp(last_m[0]):%b %Y}: last order {last_m[1]}, last calendar order day {last_cal_day} "
      f"-> complete: {LAST_MONTH_COMPLETE}; last complete month used for the grid: {LAST_COMPLETE_MONTH:%b %Y}")
pd.concat({"t1": t1.T, "t2": t2.T}).to_csv(OUT / "october_completeness_tests.csv")
t3.to_csv(OUT / "october_vs_neighbours.csv", index=False)
""")

md(r"""
## 9c2. The evidence gate (review items B3 and F4)
**What:** one table per question the review asked, saved to `stage1/evidence_*.csv` so the numbers go into the
decision log as they are:
1. rows per year after dropping duplicate parts, next to the rows each yearly file holds;
2. whether every `invoice_id` is unique, and whether any calendar order day inside the data's range has no rows;
3. returns: negative lines and their bottles as a share of positive bottles, by year (the rule: keep returns out of
   demand only if they stay under 0.5% of bottles in every year, and say figures are gross orders);
4. items carrying several bottle sizes or packs, descriptions used under several item numbers, vendor numbers with
   several names;
5. the dollar identity on clean rows (rows whose prices have cents): does `sales_dollars` equal bottles × retail
   price, or does something else (a surcharge) sit inside it; and the retail-to-cost ratio, measured rather than assumed.
6. (judge addendum 1) values that fail to cast, and negatives written with parentheses or a leading minus;
7. repaired lines whose whole-number price matches two or more cents prices in the same item-month, as a share of
   dollars by year (if any year is above 0.1%, those lines move to the price on the nearest-dated clean row);
8. the holiday calendar test: calendar order days against observed order days in every complete month. It passes if
   they agree within one day in at least 95% of months with no consistent drift in any year. Observed days are counted
   two ways, any order line and "full" days (lines at least 25% of the month's median day), because small weekend
   batches exist; the 25% cut is my choice and is reported as such.

**Why:** each of these can quietly change a forecast or a claim on the page, so each is measured once on the real data
before any model runs.
""")
code(r"""
ev = {}
ev["rows_by_year"] = con.execute('''
SELECT regexp_extract(source_part, '_(20[0-9][0-9])_', 1) AS file_year, COUNT(*) AS rows_in_file,
       SUM(CASE WHEN source_part IN (SELECT source_part FROM dropped_parts) THEN 0 ELSE 1 END) AS rows_kept
FROM raw_all GROUP BY 1 ORDER BY 1''').df()
ev["ids_and_gaps"] = con.execute('''
SELECT (SELECT COUNT(*) FROM sales) AS lines, (SELECT COUNT(DISTINCT invoice_id) FROM sales) AS distinct_invoice_ids,
       (SELECT COUNT(*) FROM calendar c WHERE c.order_day
          AND c.day BETWEEN (SELECT MIN(order_date) FROM sales) AND (SELECT MAX(order_date) FROM sales)
          AND c.day NOT IN (SELECT DISTINCT order_date FROM sales WHERE order_date IS NOT NULL)) AS calendar_days_with_no_rows''').df()
ev["returns_by_year"] = con.execute('''
SELECT year(order_date) AS year,
       SUM(CASE WHEN sales_bottles < 0 THEN 1 ELSE 0 END) AS negative_lines,
       ROUND(100.0 * SUM(CASE WHEN sales_bottles < 0 THEN 1 ELSE 0 END) / COUNT(*), 3) AS pct_lines,
       ROUND(-100.0 * SUM(CASE WHEN sales_bottles < 0 THEN sales_bottles ELSE 0 END)
             / SUM(CASE WHEN sales_bottles > 0 THEN sales_bottles ELSE 0 END), 3) AS pct_of_bottles
FROM sales WHERE order_date IS NOT NULL GROUP BY 1 ORDER BY 1''').df()
ev["identity"] = con.execute('''
SELECT
  (SELECT COUNT(DISTINCT item_no) FROM (SELECT item_no FROM sales GROUP BY item_no HAVING COUNT(DISTINCT bottle_volume_ml) > 1)) AS items_several_sizes,
  (SELECT COUNT(DISTINCT item_no) FROM (SELECT item_no FROM sales GROUP BY item_no HAVING COUNT(DISTINCT pack) > 1))             AS items_several_packs,
  (SELECT COUNT(*) FROM (SELECT im_desc FROM sales GROUP BY im_desc HAVING COUNT(DISTINCT item_no) > 1))                        AS descriptions_several_items,
  (SELECT COUNT(*) FROM (SELECT vendor_number FROM sales GROUP BY vendor_number HAVING COUNT(DISTINCT vendor_name) > 1))        AS vendor_numbers_several_names,
  (SELECT SUM(CASE WHEN bottle_volume_ml IS NULL OR bottle_volume_ml <= 0 THEN 1 ELSE 0 END) FROM sales)                         AS lines_bad_volume,
  (SELECT SUM(CASE WHEN pack IS NULL OR pack <= 0 THEN 1 ELSE 0 END) FROM sales)                                                 AS lines_bad_pack''').df()
ev["dollar_identity_clean_rows"] = con.execute('''
SELECT year(order_date) AS year, COUNT(*) AS clean_lines,
       ROUND(100.0 * AVG(CASE WHEN ABS(sales_dollars_raw - sales_bottles * state_bottle_retail_raw) <= 0.01 THEN 1.0 ELSE 0.0 END), 3) AS pct_identity_holds,
       ROUND(MEDIAN(state_bottle_retail_raw / NULLIF(state_bottle_cost_raw, 0)), 4) AS median_retail_to_cost,
       ROUND(QUANTILE_CONT(state_bottle_retail_raw / NULLIF(state_bottle_cost_raw, 0), 0.05), 4) AS p05_ratio,
       ROUND(QUANTILE_CONT(state_bottle_retail_raw / NULLIF(state_bottle_cost_raw, 0), 0.95), 4) AS p95_ratio
FROM sales
WHERE order_date IS NOT NULL AND sales_bottles > 0
  AND state_bottle_retail_raw <> floor(state_bottle_retail_raw) AND state_bottle_cost_raw <> floor(state_bottle_cost_raw)
GROUP BY 1 ORDER BY 1''').df()
ev["prices_and_dollars_by_year"] = con.execute('''
SELECT year(order_date) AS year, COUNT(*) AS lines,
       ROUND(100.0 * AVG(CASE WHEN state_bottle_retail_raw IS NULL THEN 1.0 ELSE 0.0 END), 2) AS pct_lines_no_unit_price,
       MIN(CASE WHEN state_bottle_retail_raw IS NOT NULL THEN order_date END) AS first_date_with_price,
       ROUND(100.0 * AVG(CASE WHEN sales_dollars_raw = floor(sales_dollars_raw) THEN 1.0 ELSE 0.0 END), 2) AS pct_lines_whole_dollar_total,
       ROUND(100.0 * AVG(CASE WHEN sales_liters_raw = floor(sales_liters_raw)
                               AND sales_bottles * bottle_volume_ml / 1000.0 <> floor(sales_bottles * bottle_volume_ml / 1000.0)
                              THEN 1.0 ELSE 0.0 END), 2) AS pct_lines_liters_truncated,
       ROUND(100.0 * SUM(CASE WHEN dollars_source LIKE 'state total%' THEN sales_dollars ELSE 0 END) / SUM(sales_dollars), 2) AS pct_dollars_from_state_total
FROM sales WHERE order_date IS NOT NULL GROUP BY 1 ORDER BY 1''').df()
ev["invoice_id_format_by_year"] = con.execute('''
SELECT year(order_date) AS year, regexp_replace(invoice_id, '[0-9]', '9', 'g') AS pattern, COUNT(*) AS lines,
       COUNT(DISTINCT invoice_id) AS distinct_ids
FROM sales GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER (PARTITION BY year(order_date) ORDER BY COUNT(*) DESC) <= 3
ORDER BY 1, 3 DESC''').df()
ev["store_no_leading_zeros"] = con.execute('''
SELECT COUNT(DISTINCT store_no_raw) AS raw_store_numbers,
       COUNT(DISTINCT store_no) AS after_stripping_zeros,
       (SELECT COUNT(*) FROM (SELECT store_no FROM sales GROUP BY 1 HAVING COUNT(DISTINCT store_no_raw) > 1)) AS stores_merged,
       SUM(CASE WHEN store_no_raw LIKE '0%' THEN 1 ELSE 0 END) AS lines_with_leading_zero
FROM sales''').df()
ev["store_merges"] = con.execute('''
SELECT store_no, string_agg(DISTINCT store_no_raw, ' / ') AS raw_numbers, COUNT(*) AS lines,
       MIN(order_date) AS first_order, MAX(order_date) AS last_order, COUNT(DISTINCT store_name) AS names
FROM sales GROUP BY 1 HAVING COUNT(DISTINCT store_no_raw) > 1 ORDER BY lines DESC''').df()
# decision 35: do the raw numbers that merge share a store name or an address?
ev["store_merges_shared"] = con.execute('''
WITH m AS (SELECT store_no FROM sales GROUP BY 1 HAVING COUNT(DISTINCT store_no_raw) > 1),
nm AS (SELECT store_no, upper(trim(store_name)) AS v, COUNT(DISTINCT store_no_raw) AS k FROM sales WHERE store_no IN (SELECT store_no FROM m) GROUP BY 1, 2),
ad AS (SELECT store_no, upper(trim(store_address)) AS v, COUNT(DISTINCT store_no_raw) AS k FROM sales WHERE store_no IN (SELECT store_no FROM m) GROUP BY 1, 2)
SELECT COUNT(*) AS merged_stores,
       SUM(CASE WHEN (SELECT MAX(k) FROM nm WHERE nm.store_no = m.store_no) > 1 THEN 1 ELSE 0 END) AS share_a_name,
       SUM(CASE WHEN (SELECT MAX(k) FROM ad WHERE ad.store_no = m.store_no) > 1 THEN 1 ELSE 0 END) AS share_an_address,
       SUM(CASE WHEN (SELECT MAX(k) FROM nm WHERE nm.store_no = m.store_no) > 1
                  OR (SELECT MAX(k) FROM ad WHERE ad.store_no = m.store_no) > 1 THEN 1 ELSE 0 END) AS share_name_or_address
FROM m''').df()
ev["weekday_lines_by_year"] = con.execute('''
SELECT year(order_date) AS year,
       SUM(CASE WHEN isodow(order_date) = 6 THEN 1 ELSE 0 END) AS sat_lines,
       SUM(CASE WHEN isodow(order_date) = 7 THEN 1 ELSE 0 END) AS sun_lines,
       COUNT(DISTINCT CASE WHEN isodow(order_date) >= 6 THEN order_date END) AS weekend_days_with_orders,
       ROUND(100.0 * SUM(CASE WHEN isodow(order_date) >= 6 THEN sales_bottles ELSE 0 END) / SUM(sales_bottles), 2) AS pct_bottles_on_weekends
FROM sales WHERE order_date IS NOT NULL AND sales_bottles > 0 GROUP BY 1 ORDER BY 1''').df()
# decision 34: exact full-row duplicates by year (all 23 columns equal); kept, none removed
ev["full_row_duplicates_by_year"] = con.execute('''
WITH r AS (SELECT regexp_extract(source_part, '_(20[0-9][0-9])_', 1) AS file_year,
                  md5(CAST(ROW(*COLUMNS(* EXCLUDE (source_part))) AS VARCHAR)) AS h
           FROM raw_all WHERE source_part NOT IN (SELECT source_part FROM dropped_parts))
SELECT file_year, COUNT(*) AS rows, COUNT(*) - COUNT(DISTINCT h) AS extra_copies_of_identical_rows
FROM r GROUP BY 1 ORDER BY 1''').df()
dup = con.execute('''
WITH r AS (SELECT regexp_extract(source_part, '_(20[0-9][0-9])_', 1) AS file_year, ordered_on,
                  TRY_CAST(sales_bottles AS DOUBLE) AS b,
                  md5(CAST(ROW(*COLUMNS(* EXCLUDE (source_part))) AS VARCHAR)) AS h
           FROM raw_all WHERE source_part NOT IN (SELECT source_part FROM dropped_parts)),
k AS (SELECT file_year, h, ANY_VALUE(ordered_on) AS day, ANY_VALUE(b) AS b, COUNT(*) - 1 AS extra FROM r GROUP BY 1, 2),
yb AS (SELECT file_year, SUM(CASE WHEN b > 0 THEN b ELSE 0 END) AS bottles FROM r GROUP BY 1),
dd AS (SELECT file_year, day, SUM(extra) AS extra FROM k WHERE extra > 0 GROUP BY 1, 2)
SELECT yb.file_year,
       ROUND(100.0 * COALESCE((SELECT SUM(extra * GREATEST(b, 0)) FROM k WHERE k.file_year = yb.file_year), 0) / yb.bottles, 4) AS pct_bottles_in_extra_copies,
       (SELECT COUNT(*) FROM dd WHERE dd.file_year = yb.file_year) AS dates_with_duplicates,
       ROUND(100.0 * (SELECT MAX(extra) FROM dd WHERE dd.file_year = yb.file_year)
             / NULLIF((SELECT SUM(extra) FROM dd WHERE dd.file_year = yb.file_year), 0), 1) AS pct_on_busiest_date
FROM yb ORDER BY 1''').df()
ev["full_row_duplicates_by_year"] = ev["full_row_duplicates_by_year"].merge(dup, on="file_year")
DUP_STOP = bool((ev["full_row_duplicates_by_year"].pct_bottles_in_extra_copies > 0.5).any())
print("decision 34 stop rule (exact duplicates over 0.5% of a year's bottles):", DUP_STOP,
      "| clustering: see dates_with_duplicates and pct_on_busiest_date")

# decision 37: the raw date field is a plain date (shapes of the raw text, and weekday shares)
ev["ordered_on_format"] = con.execute('''
SELECT regexp_replace(CAST(ordered_on AS VARCHAR), '[0-9]', '9', 'g') AS shape, COUNT(*) AS rows,
       MIN(CAST(ordered_on AS VARCHAR)) AS example
FROM raw_all WHERE source_part NOT IN (SELECT source_part FROM dropped_parts) GROUP BY 1 ORDER BY 2 DESC''').df()
ev["weekday_share_of_lines"] = con.execute('''
SELECT dayname(order_date) AS weekday, isodow(order_date) AS dow, COUNT(*) AS lines,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_lines
FROM sales WHERE order_date IS NOT NULL GROUP BY 1, 2 ORDER BY 2''').df()

# B3 item keys and the 1% link line: bottles in the trailing 12 months on item numbers that took over an older item
# number with the same description and bottle size (a relaunch under a new number). Linking is required before
# stage 2 only if this exceeds 1% of trailing-12-month bottles.
T12_END = LAST_COMPLETE_MONTH + pd.offsets.MonthEnd(0)
T12_START = LAST_COMPLETE_MONTH - pd.offsets.MonthBegin(11)
ev["item_link_check"] = con.execute('''
WITH it AS (
    SELECT upper(trim(im_desc)) AS d, bottle_volume_ml AS ml, item_no, MIN(order_date) AS first_order, MAX(order_date) AS last_order,
           SUM(CASE WHEN order_date BETWEEN ? AND ? AND sales_bottles > 0 THEN sales_bottles ELSE 0 END) AS b12
    FROM sales WHERE order_date IS NOT NULL GROUP BY 1, 2, 3
),
succ AS (
    SELECT a.item_no, a.b12,
           MAX(CASE WHEN b.first_order < a.first_order THEN 1 ELSE 0 END) AS has_older,
           MAX(CASE WHEN b.first_order < a.first_order AND b.last_order <= a.first_order + INTERVAL 90 DAY THEN 1 ELSE 0 END) AS handover
    FROM it a JOIN it b ON a.d = b.d AND a.ml = b.ml AND a.item_no <> b.item_no
    GROUP BY 1, 2
)
SELECT (SELECT SUM(b12) FROM it) AS trailing12_bottles,
       (SELECT COUNT(*) FROM succ WHERE has_older = 1) AS newer_numbers_same_desc_size,
       ROUND(100.0 * (SELECT SUM(b12) FROM succ WHERE has_older = 1) / (SELECT SUM(b12) FROM it), 3) AS pct_t12_bottles_any_older,
       (SELECT COUNT(*) FROM succ WHERE handover = 1) AS newer_numbers_handover,
       ROUND(100.0 * (SELECT SUM(b12) FROM succ WHERE handover = 1) / (SELECT SUM(b12) FROM it), 3) AS pct_t12_bottles_handover,
       ROUND(100.0 * (SELECT SUM(b12) FROM it WHERE item_no IN (SELECT item_no FROM sales GROUP BY 1 HAVING COUNT(DISTINCT bottle_volume_ml) > 1))
             / (SELECT SUM(b12) FROM it), 3) AS pct_t12_bottles_items_several_sizes,
       ROUND(100.0 * (SELECT SUM(b12) FROM it WHERE item_no IN (SELECT item_no FROM sales GROUP BY 1 HAVING COUNT(DISTINCT pack) > 1))
             / (SELECT SUM(b12) FROM it), 3) AS pct_t12_bottles_items_several_packs
''', [T12_START.date(), T12_END.date()]).df()
print("1% link line: linking needed before stage 2:", bool(ev["item_link_check"].pct_t12_bottles_handover.iloc[0] > 1),
      "(handover definition: the older number's last order within 90 days after the newer one's first; my choice)")
ev["vendor_numbers_several_names"] = con.execute('''
SELECT vendor_number, string_agg(DISTINCT vendor_name, ' | ') AS names, COUNT(DISTINCT vendor_name) AS n_names,
       COUNT(*) AS lines, MIN(order_date) AS first_order, MAX(order_date) AS last_order
FROM sales GROUP BY 1 HAVING COUNT(DISTINCT vendor_name) > 1 ORDER BY lines DESC''').df()

# decision 32: dollars by source by year, and the loss bound for lines that keep the state's (possibly truncated) total
ev["dollars_by_source_by_year"] = con.execute('''
SELECT year(order_date) AS year, dollars_source, COUNT(*) AS lines, ROUND(SUM(sales_dollars), 2) AS dollars,
       ROUND(100.0 * SUM(sales_dollars) / SUM(SUM(sales_dollars)) OVER (PARTITION BY year(order_date)), 3) AS pct_of_year_dollars
FROM sales WHERE order_date IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2''').df()
ev["dollar_loss_bound_by_year"] = con.execute('''
SELECT year(order_date) AS year,
       ROUND(SUM(CASE WHEN dollars_source LIKE 'state total%' THEN sales_dollars ELSE 0 END), 2) AS dollars_kept,
       ROUND(SUM(CASE WHEN dollars_source LIKE 'repaired%' THEN sales_dollars - sales_dollars_raw ELSE 0 END), 2) AS dollars_added_by_repair,
       SUM(CASE WHEN dollars_source LIKE 'repaired%' THEN 1 ELSE 0 END) AS lines_repaired,
       SUM(CASE WHEN dollars_source = 'state total (whole number)' THEN 1 ELSE 0 END) AS kept_whole_number_lines,
       ROUND(100.0 * SUM(CASE WHEN dollars_source = 'state total (whole number)' AND sales_bottles > 0 THEN 1 ELSE 0 END)
             / SUM(sales_dollars), 4) AS loss_bound_pct_of_dollars,
       ROUND(100.0 * AVG(CASE WHEN sales_dollars_raw = floor(sales_dollars_raw) THEN 1.0 ELSE 0.0 END), 2) AS pct_lines_whole_dollar_total
FROM sales WHERE order_date IS NOT NULL GROUP BY 1 ORDER BY 1''').df()

# values that fail to cast, and negatives written with parentheses or a leading minus (judge addendum 1, decision 26)
num_cols = ["ordered_on", "pack", "bottle_volume_ml", "state_bottle_cost", "state_bottle_retail",
            "sales_bottles", "sales_dollars", "sales_liters", "sales_gallons"]
def _cast(c):
    v = f"replace(replace(trim(CAST({c} AS VARCHAR)), '$', ''), ',', '')"
    if c == "ordered_on":
        return f"COALESCE(TRY_CAST({v} AS DATE), TRY_CAST(try_strptime({v}, '%m/%d/%Y') AS DATE))"
    return f"TRY_CAST({v} AS DOUBLE)"
ev["cast_failures"] = con.execute(" UNION ALL ".join(f'''
SELECT '{c}' AS column_name,
       SUM(CASE WHEN {c} IS NOT NULL AND trim(CAST({c} AS VARCHAR)) <> '' AND {_cast(c)} IS NULL THEN 1 ELSE 0 END) AS fail_to_cast,
       SUM(CASE WHEN {c} IS NULL OR trim(CAST({c} AS VARCHAR)) = '' THEN 1 ELSE 0 END) AS blank,
       SUM(CASE WHEN trim(CAST({c} AS VARCHAR)) LIKE '(%' THEN 1 ELSE 0 END) AS parentheses,
       SUM(CASE WHEN replace(trim(CAST({c} AS VARCHAR)), '$', '') LIKE '-%' THEN 1 ELSE 0 END) AS leading_minus
FROM raw_all WHERE source_part NOT IN (SELECT source_part FROM dropped_parts)''' for c in num_cols)).df()

# repaired lines whose whole price matches two or more cents prices in the same item-month (judge addendum 1, decision 25)
ev["same_floor_cents_by_year"] = con.execute('''
WITH amb AS (
    SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS m, floor(state_bottle_retail_raw) AS fl
    FROM sales
    WHERE order_date IS NOT NULL AND state_bottle_retail_raw <> floor(state_bottle_retail_raw)
    GROUP BY 1, 2, 3 HAVING COUNT(DISTINCT state_bottle_retail_raw) > 1
)
SELECT year(s.order_date) AS year,
       SUM(CASE WHEN a.item_no IS NOT NULL AND s.dollars_source IN ('repaired total (same-month price)', 'repaired total (nearest-date price)') THEN 1 ELSE 0 END) AS ambiguous_lines,
       SUM(CASE WHEN a.item_no IS NOT NULL AND s.dollars_source IN ('repaired total (same-month price)', 'repaired total (nearest-date price)') THEN s.sales_dollars ELSE 0 END) AS ambiguous_dollars,
       SUM(s.sales_dollars) AS dollars,
       ROUND(100.0 * SUM(CASE WHEN a.item_no IS NOT NULL AND s.dollars_source IN ('repaired total (same-month price)', 'repaired total (nearest-date price)') THEN s.sales_dollars ELSE 0 END)
             / SUM(s.sales_dollars), 4) AS pct_of_dollars
FROM sales s
LEFT JOIN amb a ON a.item_no = s.item_no AND a.m = CAST(date_trunc('month', s.order_date) AS DATE)
               AND a.fl = s.state_bottle_retail_raw
WHERE s.order_date IS NOT NULL GROUP BY 1 ORDER BY 1''').df()

# holiday calendar test (judge addendum 1, decision 29): calendar order days vs observed order days per complete month.
# Observed is counted two ways: every date with any order line, and "full" days only (lines >= 25% of the month's
# median daily lines), because small weekend batches would otherwise count as whole order days.
cal_m = con.execute('''
WITH od AS (SELECT CAST(date_trunc('month', day) AS DATE) AS m, SUM(CASE WHEN order_day THEN 1 ELSE 0 END) AS calendar_days
            FROM calendar GROUP BY 1),
dl AS (SELECT order_date AS day, CAST(date_trunc('month', order_date) AS DATE) AS m, COUNT(*) AS n,
              SUM(CASE WHEN sales_bottles > 0 THEN sales_bottles ELSE 0 END) AS b
       FROM sales WHERE order_date IS NOT NULL GROUP BY 1, 2),
med AS (SELECT m, MEDIAN(n) AS med_n FROM dl GROUP BY 1)
SELECT dl.m AS month, year(dl.m) AS year, od.calendar_days,
       COUNT(*) AS days_any_orders,
       SUM(CASE WHEN dl.n >= 0.25 * med.med_n THEN 1 ELSE 0 END) AS days_full_orders,
       SUM(CASE WHEN c.order_day THEN 0 ELSE 1 END) AS order_dates_off_calendar,
       SUM(dl.b) AS bottles, SUM(CASE WHEN c.order_day THEN 0 ELSE dl.b END) AS bottles_off_calendar
FROM dl JOIN med USING (m) JOIN od USING (m) LEFT JOIN calendar c ON c.day = dl.day
WHERE dl.m >= DATE '2012-01-01' AND dl.m <= ?
GROUP BY 1, 2, 3 ORDER BY 1''', [LAST_COMPLETE_MONTH.date()]).df()
cal_m["diff_any"] = cal_m.days_any_orders - cal_m.calendar_days
cal_m["diff_full"] = cal_m.days_full_orders - cal_m.calendar_days
cal_m.to_csv(OUT / "calendar_vs_observed_by_month.csv", index=False)
g = cal_m.groupby("year")
ev["calendar_test_by_year"] = pd.DataFrame({
    "months": g.size(),
    "pct_within_1_any": (g.diff_any.apply(lambda x: (x.abs() <= 1).mean()) * 100).round(1),
    "mean_diff_any": g.diff_any.mean().round(2),
    "pct_within_1_full": (g.diff_full.apply(lambda x: (x.abs() <= 1).mean()) * 100).round(1),
    "mean_diff_full": g.diff_full.mean().round(2),
    "min_diff_full": g.diff_full.min(), "max_diff_full": g.diff_full.max(),
    "share_months_full_above": (g.diff_full.apply(lambda x: (x > 0).mean()) * 100).round(1),
    "share_months_full_below": (g.diff_full.apply(lambda x: (x < 0).mean()) * 100).round(1),
    "pct_bottles_off_calendar": (100 * g.bottles_off_calendar.sum() / g.bottles.sum()).round(3),
}).reset_index()
for kind in ["any", "full"]:
    print(f"calendar within 1 day ({kind} orders): {100 * (cal_m[f'diff_{kind}'].abs() <= 1).mean():.1f}% of "
          f"{len(cal_m)} complete months (rule: at least 95%, no consistent drift in any year)")
# decision 36 pass rule, on the full-day count. "Consistent drift" in a year = at least 75% of its months off in the
# same direction (my operational reading, reported as such).
ct = ev["calendar_test_by_year"]
cal_within = 100 * (cal_m.diff_full.abs() <= 1).mean()
drift_years = ct.loc[(ct.share_months_full_above >= 75) | (ct.share_months_full_below >= 75), "year"].tolist()
off_years = ct.loc[ct.pct_bottles_off_calendar >= 2, "year"].tolist()
CALENDAR_PASSES = bool(cal_within >= 95 and not drift_years and not off_years)
print(f"calendar test (decision 36): within 1 day {cal_within:.1f}%, drift years {drift_years}, "
      f"years with >=2% bottles off calendar {off_years} -> pass: {CALENDAR_PASSES}")
print("order-day rule used for bottles_per_order_day:", "calendar" if CALENDAR_PASSES else
      "calendar kept in bottles_per_order_day; effective order days (below) are the rule for stage 2")

# effective order days (decision 36 fallback): per month, sum over weekdays of (days of that weekday, holidays removed,
# up to the last order date) x that weekday's share of bottles over the 24 months before the origin, x 5,
# so a standard Monday-Sunday week counts 5.
# Addendum 3 (decision 43): bottles on each listed holiday, by year. A holiday "carries orders" in a year when its
# bottles are at least 25% of the median bottles of that month's order dates (the full-day line used above); a holiday
# that carries orders in at least half of the years it falls on a weekday is dropped from the holiday list for
# effective order days (the 25% and half-of-years cut-offs are my operational reading, reported as such).
hn = [{"day": d, "holiday": n} for y in range(2012, 2027) for d, n in iowa_holidays_named(y).items()
      if d.weekday() < 5 and pd.Timestamp("2012-01-01").date() <= d <= (LAST_COMPLETE_MONTH + pd.offsets.MonthEnd(0)).date()]
hn_df = pd.DataFrame(hn)
con.register("hn_df", hn_df)
hol_rep = con.execute('''
WITH db AS (SELECT order_date AS day, SUM(CASE WHEN sales_bottles > 0 THEN sales_bottles ELSE 0 END) AS b
            FROM sales WHERE order_date IS NOT NULL GROUP BY 1),
med AS (SELECT date_trunc('month', day) AS m, MEDIAN(b) AS med_b FROM db GROUP BY 1)
SELECT year(h.day) AS year, h.holiday, CAST(h.day AS DATE) AS day, COALESCE(db.b, 0) AS bottles,
       ROUND(COALESCE(db.b, 0) / med.med_b, 3) AS ratio_to_month_median_day,
       COALESCE(db.b, 0) >= 0.25 * med.med_b AS carries_orders
FROM hn_df h LEFT JOIN db ON db.day = CAST(h.day AS DATE) JOIN med ON med.m = date_trunc('month', CAST(h.day AS DATE))
ORDER BY 1, 3''').df()
hol_rep.to_csv(OUT / "holiday_bottles_by_year.csv", index=False)
hol_sum = hol_rep.groupby("holiday").agg(years=("year", "size"), years_carrying_orders=("carries_orders", "sum"),
                                         median_ratio=("ratio_to_month_median_day", "median")).reset_index()
hol_sum["dropped"] = hol_sum.years_carrying_orders >= 0.5 * hol_sum.years
HOL_DROPPED = hol_sum.loc[hol_sum.dropped, "holiday"].tolist()
print("holidays (bottles vs the month's median order day):"); display(hol_sum)
print("holidays dropped from the effective-order-day list (carry orders in at least half of years):", HOL_DROPPED or "none")
EFF_HOL = {d for y in range(2011, 2028) for d, n in iowa_holidays_named(y).items() if n not in HOL_DROPPED}
cal["eff_order_day"] = [(d.weekday() < 5) and (d not in EFF_HOL) for d in cal.day]
con.execute("CREATE OR REPLACE TABLE calendar_eff AS SELECT CAST(day AS DATE) AS day, eff_order_day FROM cal")
con.execute('''
CREATE OR REPLACE TABLE month_weekday_days AS
SELECT CAST(date_trunc('month', day) AS DATE) AS month_start, isodow(day) AS dow,
       SUM(CASE WHEN isodow(day) >= 6 OR eff_order_day THEN 1 ELSE 0 END) AS days
FROM calendar_eff WHERE day <= (SELECT MAX(order_date) FROM sales) GROUP BY 1, 2''')
con.execute('''
CREATE OR REPLACE TABLE month_weekday_bottles AS
SELECT CAST(date_trunc('month', order_date) AS DATE) AS month_start, isodow(order_date) AS dow, SUM(sales_bottles) AS bottles
FROM sales WHERE order_date IS NOT NULL AND sales_bottles > 0 GROUP BY 1, 2''')
FIRST_DATA_MONTH = pd.Timestamp(con.execute("SELECT MIN(month_start) FROM month_weekday_bottles").fetchone()[0])
def effective_order_days(origin):
    # effective order days per month, using weekday shares from the 24 months before `origin` (a month start).
    # Addendum 3: an origin in the first 24 months of data uses the earliest 24 months' shares instead.
    o = max(pd.Timestamp(origin), FIRST_DATA_MONTH + pd.DateOffset(months=24)).date()
    return con.execute('''
    WITH sh AS (
        SELECT dow, SUM(bottles) / SUM(SUM(bottles)) OVER () AS share
        FROM month_weekday_bottles
        WHERE month_start < ? AND month_start >= CAST(? - INTERVAL 24 MONTH AS DATE) GROUP BY dow
    )
    SELECT d.month_start, 5 * SUM(d.days * COALESCE(sh.share, 0)) AS effective_order_days
    FROM month_weekday_days d LEFT JOIN sh USING (dow) GROUP BY 1 ORDER BY 1''', [o, o]).df()
EFF_ORIGIN = LAST_COMPLETE_MONTH + pd.offsets.MonthBegin(1)
eff_last = effective_order_days(EFF_ORIGIN)
eff_cmp = eff_last.merge(cal_m[["month", "calendar_days", "days_full_orders"]], left_on="month_start", right_on="month", how="left")
eff_cmp.to_csv(OUT / "effective_order_days_last_origin.csv", index=False)
print(f"effective order days with weekday shares from the 24 months before {EFF_ORIGIN:%b %Y} (last 14 months):")
display(eff_cmp.drop(columns="month").tail(14).round(2))

for k, v in ev.items():
    print(k); display(v); v.to_csv(OUT / f"evidence_{k}.csv", index=False)
print("returns rule (under 0.5% of bottles every year):", bool((ev["returns_by_year"].pct_of_bottles < 0.5).all()))
""")

md(r"""
## 9d. Monthly demand per product (the main modeling table)
**What:** one row per item per calendar month, from the item's first order month to the last data month,
with zeros where it had no orders. Columns: bottles (the forecast target), liters and 9-liter cases (from bottles ×
bottle size, never from the state's truncated liters column), physical cases (bottles ÷ pack), dollars at state
retail and at state cost (repaired prices), the statewide calendar order days of the month, and two flags: the
item's launch month (a partial month when the first order came after the month's first order day) and
`month_complete`. If October 2026 is ruled incomplete (9c) it stays in as an input, flagged, with its order days
counted only up to the last order date, so bottles per order day stays comparable; it is left out of the frozen test.
**Why:** stopping each item at its *last* order would hide that it stopped selling: a model would never see the zeros
after a product fades out, and the test would quietly skip its misses. Filling every item to the last complete month
keeps those zeros. Order days come from the calendar, the same count for every item, because a per-item count of
days with orders is part of the answer and must never be an input.
""")
code(r"""
con.execute(f'''
CREATE OR REPLACE TABLE product_month AS
WITH im AS (
    SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS month_start,
           SUM(sales_bottles)                     AS bottles,
           SUM(sales_liters)                      AS liters,
           SUM(cases_9l)                          AS cases_9l,
           SUM(physical_cases)                    AS physical_cases,
           SUM(sales_dollars)                     AS dollars_retail,
           MEDIAN(CASE WHEN NOT zero_dollar_line THEN sales_dollars / sales_bottles END) AS avg_price_paid_per_bottle   -- decision 33: average price stores paid per bottle, item-month median
    FROM sales
    WHERE sales_bottles > 0 AND order_date IS NOT NULL
    GROUP BY item_no, month_start
),
first_order AS (SELECT item_no, MIN(order_date) AS first_order_date FROM sales WHERE sales_bottles > 0 GROUP BY item_no),
months AS (
    SELECT CAST(date_trunc('month', day) AS DATE) AS month_start,
           SUM(CASE WHEN order_day AND day <= (SELECT MAX(order_date) FROM sales) THEN 1 ELSE 0 END) AS calendar_order_days,
           MIN(CASE WHEN order_day THEN day END)       AS first_order_day
    FROM calendar GROUP BY 1
),
grid AS (
    SELECT f.item_no, m.month_start, m.calendar_order_days, m.first_order_day, f.first_order_date
    FROM first_order f JOIN months m
      ON m.month_start >= CAST(date_trunc('month', f.first_order_date) AS DATE)
     AND m.month_start <= (SELECT CAST(date_trunc('month', MAX(order_date)) AS DATE) FROM sales)
)
SELECT g.item_no, g.month_start, g.calendar_order_days,
       COALESCE(im.bottles, 0) AS bottles, COALESCE(im.liters, 0) AS liters, COALESCE(im.cases_9l, 0) AS cases_9l,
       COALESCE(im.physical_cases, 0) AS physical_cases,
       COALESCE(im.dollars_retail, 0) AS dollars_retail, im.avg_price_paid_per_bottle,
       COALESCE(im.bottles, 0) * 1.0 / g.calendar_order_days AS bottles_per_order_day,
       (g.month_start = CAST(date_trunc('month', g.first_order_date) AS DATE)
        AND g.first_order_date > g.first_order_day) AS partial_launch_month,
       g.month_start <= DATE '{LAST_COMPLETE_MONTH:%Y-%m-%d}' AS month_complete
FROM grid g LEFT JOIN im ON im.item_no = g.item_no AND im.month_start = g.month_start
''')

# Acceptance test B1: sums equal the cleaned rows by year (inside the grid's months), every item ends on the last complete month
acc = con.execute(f'''
SELECT y.year, y.rows_bottles, p.grid_bottles, y.rows_bottles = p.grid_bottles AS equal
FROM (SELECT year(order_date) AS year, SUM(sales_bottles) AS rows_bottles FROM sales
      WHERE sales_bottles > 0 AND order_date IS NOT NULL GROUP BY 1) y
JOIN (SELECT year(month_start) AS year, SUM(bottles) AS grid_bottles FROM product_month GROUP BY 1) p USING (year)
ORDER BY 1''').df()
display(acc)
display(con.execute(f'''
SELECT COUNT(DISTINCT item_no) AS items, COUNT(*) AS product_months,
       AVG(CASE WHEN bottles = 0 THEN 1.0 ELSE 0.0 END) AS zero_share,
       SUM(CASE WHEN partial_launch_month THEN 1 ELSE 0 END) AS partial_launch_months,
       (SELECT COUNT(*) FROM (SELECT item_no FROM product_month GROUP BY item_no
                              HAVING MAX(month_start) <> (SELECT MAX(month_start) FROM product_month))) AS items_not_ending_on_last_month
FROM product_month''').df().T)
print("for comparison, the old grid (first to LAST ORDER month only):")
display(con.execute('''
SELECT COUNT(*) AS product_months_old, AVG(CASE WHEN bottles = 0 THEN 1.0 ELSE 0.0 END) AS zero_share_old
FROM product_month p
JOIN (SELECT item_no, MAX(month_start) AS last_m FROM product_month WHERE bottles > 0 GROUP BY item_no) l USING (item_no)
WHERE p.month_start <= l.last_m''').df().T)
""")

md(r"""
## 9e. Vendor per item and month, and the display label
**What:** `item_vendor_month` records the most common vendor number on each item's orders in each month (ties go to
more bottles, then the lower vendor number). The display label `item_vendor` is the most common vendor over the item's
last three months with orders.
**Why:** brands move between suppliers. A model may only use the vendor as it was known at the forecast origin, so the
monthly record lets stage 2 look it up as of any origin; the label is for the page only and is never a model input.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE item_vendor_month AS
SELECT item_no, month_start, vendor_number, vendor_name FROM (
    SELECT item_no, CAST(date_trunc('month', order_date) AS DATE) AS month_start, vendor_number,
           MIN(vendor_name) AS vendor_name, COUNT(*) AS n, SUM(sales_bottles) AS b,
           ROW_NUMBER() OVER (PARTITION BY item_no, CAST(date_trunc('month', order_date) AS DATE)
                              ORDER BY COUNT(*) DESC, SUM(sales_bottles) DESC, vendor_number) AS rn
    FROM sales WHERE order_date IS NOT NULL AND sales_bottles > 0
    GROUP BY item_no, CAST(date_trunc('month', order_date) AS DATE), vendor_number
) WHERE rn = 1
''')
con.execute('''
CREATE OR REPLACE TABLE item_vendor AS
WITH last3 AS (
    SELECT item_no, month_start, vendor_number, vendor_name,
           ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY month_start DESC) AS k
    FROM item_vendor_month
),
pick AS (
    SELECT item_no, vendor_number, MIN(vendor_name) AS vendor_name, COUNT(*) AS months, MAX(month_start) AS latest,
           ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY COUNT(*) DESC, MAX(month_start) DESC) AS rn
    FROM last3 WHERE k <= 3 GROUP BY item_no, vendor_number
)
SELECT p.item_no, p.vendor_number AS current_vendor_number, p.vendor_name AS current_vendor_name,
       (SELECT COUNT(DISTINCT vendor_number) FROM item_vendor_month v WHERE v.item_no = p.item_no) AS vendors_over_time
FROM pick p WHERE rn = 1
''')
con.execute('''
SELECT COUNT(*) AS items,
       SUM(CASE WHEN vendors_over_time > 1 THEN 1 ELSE 0 END) AS items_that_changed_vendor,
       COUNT(DISTINCT current_vendor_number) AS current_vendors
FROM item_vendor''').df()
""")

md(r"""
## 9f. Monthly demand classes at the last origin, and history length
**What:** the SBC class of each active item on its monthly bottles over the 24 months before the origin, with the
protocol's edge rule (fewer than 6 non-zero months = "too short", modeled as intermittent). Stage 2 recomputes this at
every origin; this cell shows it once, at the last complete month, so the class counts can be reported. It also counts
active items (an order in the trailing 12 months) with under 24 months of history.
**Why:** the class picks the model pool, so it must only use data available at the origin. The cut-offs (1.32 and 0.49,
Syntetos, Boylan and Croston 2005) are a convention, not a law; Kostenko and Hyndman (2006) give an alternative.
""")
code(r"""
def class_counts(origin):
    o = pd.Timestamp(origin)
    w0, w1 = (o - pd.DateOffset(months=23)).strftime("%Y-%m-%d"), o.strftime("%Y-%m-%d")
    a0 = (o - pd.DateOffset(months=11)).strftime("%Y-%m-%d")
    return con.execute(f'''
    WITH active AS (SELECT DISTINCT item_no FROM product_month
                    WHERE month_start BETWEEN DATE '{a0}' AND DATE '{w1}' AND bottles > 0),
    s AS (
        SELECT p.item_no, COUNT(*) AS n_months,
               SUM(CASE WHEN bottles > 0 THEN 1 ELSE 0 END) AS nz,
               AVG(CASE WHEN bottles > 0 THEN bottles END) AS mean_size,
               STDDEV_SAMP(CASE WHEN bottles > 0 THEN bottles END) AS sd_size,
               SUM(bottles) AS total_bottles, SUM(dollars_retail) AS dollars
        FROM product_month p JOIN active USING (item_no)
        WHERE p.month_start BETWEEN DATE '{w0}' AND DATE '{w1}'
        GROUP BY p.item_no
    )
    SELECT *, n_months * 1.0 / NULLIF(nz, 0) AS adi, POWER(sd_size / mean_size, 2) AS cv2,
           CASE WHEN nz < 6 THEN 'too short'
                WHEN n_months * 1.0 / nz < 1.32 AND POWER(sd_size / mean_size, 2) < 0.49 THEN 'smooth'
                WHEN n_months * 1.0 / nz < 1.32 THEN 'erratic'
                WHEN POWER(sd_size / mean_size, 2) < 0.49 THEN 'intermittent'
                ELSE 'lumpy' END AS sbc_class
    FROM s''').df()

cls_m = class_counts(LAST_COMPLETE_MONTH)
cls_m.to_csv(OUT / "monthly_classes_last_origin.csv", index=False)
con.execute("CREATE OR REPLACE TABLE item_sbc_monthly AS SELECT item_no, adi, cv2, sbc_class AS sbc_class_monthly FROM cls_m")
summary = cls_m.groupby("sbc_class").agg(items=("item_no", "size"), dollars=("dollars", "sum"), bottles=("total_bottles", "sum"))
summary["pct_dollars"] = (100 * summary.dollars / summary.dollars.sum()).round(1)
display(summary)
hist = con.execute(f'''
SELECT COUNT(*) AS active_items,
       SUM(CASE WHEN months_of_history < 24 THEN 1 ELSE 0 END) AS under_24_months,
       SUM(CASE WHEN months_of_history < 12 THEN 1 ELSE 0 END) AS under_12_months
FROM (SELECT item_no, COUNT(*) AS months_of_history FROM product_month GROUP BY item_no) h
WHERE item_no IN (SELECT item_no FROM product_month WHERE bottles > 0
                  AND month_start > DATE '{LAST_COMPLETE_MONTH:%Y-%m-%d}' - INTERVAL 12 MONTH)''').df()
display(hist.T)
""")

md(r"""
## 9g. Linked product series (decision 42): the unit that is forecast
**What:** the state sometimes gives a product a new item number. This block links such numbers into one **series**:
item numbers that share a description (upper-cased, spaces trimmed) and bottle size, where the newer number's first
order comes after the older one's first order and the older number's last order falls from 90 days before to 90 days
after the newer one's first (protocol 1.4, Addendum 3). A link is an **overlap** when the older number was still
ordered on or after the newer one's first order, else a **gap**; the two are reported separately. A link is made by
rule only when it is **one to one** (the newer number has exactly one such older number, and that older number has no
other newer candidate); every other candidate pair is left unlinked and listed in `ambiguous_links.csv`, and only the
ones in the top chains are decided by hand (`HAND_LINKS`). The series id is the oldest item number in the chain. Links
where the category differs are flagged, not blocked. `link_items` can be rerun on a later file with the frozen links
kept (`prior`), and lists every link made after the freeze (`links_made_after_freeze.csv`).

Each item's description, size and category are its most common ones by order lines (ties: the latest).
**Why:** 4.7% of recent bottles sit on renumbered items (stage 1 evidence). Without linking, a renumbered product looks
like a discontinued item plus a new one, and both would be forecast and scored wrongly. The 90-day window is a
judgment call, reported as such.
""")
code(r"""
items_attr = con.execute('''
WITH a AS (
    SELECT item_no, upper(trim(regexp_replace(im_desc, '\\s+', ' ', 'g'))) AS d, bottle_volume_ml AS ml, category_name,
           COUNT(*) AS n, MAX(order_date) AS latest
    FROM sales WHERE order_date IS NOT NULL AND sales_bottles > 0 GROUP BY 1, 2, 3, 4
),
pick AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY n DESC, latest DESC, d, ml, category_name) AS rn FROM a),
span AS (SELECT item_no, MIN(order_date) AS first_order, MAX(order_date) AS last_order
         FROM sales WHERE order_date IS NOT NULL AND sales_bottles > 0 GROUP BY 1),
mo AS (SELECT item_no, date_trunc('month', order_date) AS m FROM sales
       WHERE order_date IS NOT NULL AND sales_bottles > 0 GROUP BY 1, 2),
rk AS (SELECT item_no, m, ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY m DESC) AS rl,
              ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY m) AS rf, COUNT(*) OVER (PARTITION BY item_no) AS n_months FROM mo),
px AS (SELECT l.item_no,
              MEDIAN(CASE WHEN r.rl <= 12 AND NOT l.zero_dollar_line THEN l.sales_dollars / l.sales_bottles END) AS price_last12,
              MEDIAN(CASE WHEN r.rf <= 12 AND NOT l.zero_dollar_line THEN l.sales_dollars / l.sales_bottles END) AS price_first12,
              ANY_VALUE(r.n_months) AS months_with_orders
       FROM sales l JOIN rk r ON r.item_no = l.item_no AND r.m = date_trunc('month', l.order_date)
       WHERE l.order_date IS NOT NULL AND l.sales_bottles > 0 GROUP BY 1)
SELECT p.item_no, p.d, p.ml, p.category_name, s.first_order, s.last_order, x.price_last12, x.price_first12,
       x.months_with_orders
FROM pick p JOIN span s USING (item_no) JOIN px x USING (item_no) WHERE p.rn = 1''').df()
items_attr["first_order"] = pd.to_datetime(items_attr.first_order)
items_attr["last_order"] = pd.to_datetime(items_attr.last_order)

HAND_LINKS = {}   # {newer item_no: older item_no} decided by hand for ambiguous cases in the top chains
HAND_NOT_LINKED = set()   # newer item numbers decided by hand to stay separate

PRICE_BAND = (0.67, 1.5)   # decision 46 (fixed, not tuned again): older's median dollars per bottle over its last 12
                            # months with orders / newer's median over its first 12 months with orders

def link_items(items, prior=None, hand=None, window_days=90, price_band=PRICE_BAND):
    # items: item_no, d, ml, category_name, first_order, last_order.
    # prior: frozen {newer: older} links, kept as they are. hand: {newer: older} decided by hand.
    # Candidate pair (older a, newer b): same d and ml, a starts before b, and a's last order falls from window_days
    # before to window_days after b's first order. "overlap" if a's last order is on or after b's first, else "gap".
    # A rule link is made only when the pair is one to one: b has exactly one candidate and a is a candidate for no
    # other newer number. Every other candidate pair is returned as ambiguous.
    prior, hand = dict(prior or {}), dict(hand or {})
    fixed = {**prior, **hand}
    fixed_new, fixed_old = set(fixed), set(fixed.values())
    win = pd.Timedelta(days=window_days)
    rows = []
    for _, g in items.groupby(["d", "ml"], sort=True):
        if len(g) < 2:
            continue
        recs = g.to_dict("records")
        for b in recs:
            if b["item_no"] in fixed_new or b["item_no"] in HAND_NOT_LINKED:
                continue
            for a in recs:
                if (a["item_no"] != b["item_no"] and a["item_no"] not in fixed_old and a["first_order"] < b["first_order"]
                        and b["first_order"] - win <= a["last_order"] <= b["first_order"] + win):
                    ratio = a["price_last12"] / b["price_first12"] if b["price_first12"] > 0 else np.nan
                    rows.append((b["item_no"], a["item_no"], "overlap" if a["last_order"] >= b["first_order"] else "gap",
                                 (a["last_order"] - b["first_order"]).days, ratio,
                                 min(a["months_with_orders"], b["months_with_orders"]) < 3))
    cand_all = pd.DataFrame(rows, columns=["newer", "older", "kind", "older_last_minus_newer_first_days", "price_ratio",
                                           "price_thin"])
    def one2one(c):
        c = c.copy()
        c["n_older_for_newer"] = c.groupby("newer").older.transform("size")
        c["n_newer_for_older"] = c.groupby("older").newer.transform("size")
        c["one_to_one"] = (c.n_older_for_newer == 1) & (c.n_newer_for_older == 1)
        return c
    cand_all = one2one(cand_all)    # the Addendum 3 rule without the price guard, kept for the removed-links report
    in_band = cand_all.price_ratio.between(*price_band) if price_band else pd.Series(True, index=cand_all.index)
    cand = one2one(cand_all.loc[in_band, cand_all.columns[:6]])
    rule = dict(zip(cand.loc[cand.one_to_one, "newer"], cand.loc[cand.one_to_one, "older"]))
    links = {**rule, **fixed}
    src = {**{n: "rule" for n in rule}, **{n: "hand" for n in hand}, **{n: "frozen" for n in prior}}
    span = items.set_index("item_no")[["first_order", "last_order"]]
    def root(i):
        seen = set()
        while i in links and i not in seen:
            seen.add(i); i = links[i]
        return i
    cat = dict(zip(items.item_no, items.category_name))
    out = items[["item_no", "d", "ml", "category_name", "first_order", "last_order"]].copy()
    out["predecessor"] = out.item_no.map(links)
    out["series_id"] = out.item_no.map(root)
    out["link_source"] = out.item_no.map(src)
    pl = out.predecessor.map(span.last_order)
    out["link_kind"] = np.where(out.predecessor.isna(), None, np.where(pl >= out.first_order, "overlap", "gap"))
    out["link_category_differs"] = out.predecessor.notna() & (out.predecessor.map(cat) != out.category_name)
    ck = cand[cand.one_to_one].set_index("newer")
    out["link_price_ratio"] = out.item_no.map(ck.price_ratio).where(out.link_source == "rule")
    out["link_price_thin"] = out.item_no.map(ck.price_thin).where(out.link_source == "rule").fillna(False).astype(bool)
    new_links = [(n, o) for n, o in links.items() if prior.get(n) != o]
    removed = cand_all[cand_all.one_to_one & ~cand_all.newer.isin(list(rule))].reset_index(drop=True)
    return out, new_links, cand.loc[~cand.one_to_one].reset_index(drop=True), cand_all, removed

item_series, new_links, ambiguous, cand_all, removed_links = link_items(items_attr, hand=HAND_LINKS)
# register the DataFrame under its own name: "FROM item_series" would read the old table on a rerun
con.register("item_series_df", item_series)
con.execute("CREATE OR REPLACE TABLE item_series AS SELECT * FROM item_series_df")
item_series.to_csv(OUT / "item_series.csv", index=False)
pd.DataFrame(new_links, columns=["newer", "older"]).to_csv(OUT / "links_made_after_freeze.csv", index=False)

# chains: series with more than one item number, ranked by dollars in the trailing 12 months
T12_END = LAST_COMPLETE_MONTH + pd.offsets.MonthEnd(0)
T12_START = LAST_COMPLETE_MONTH - pd.offsets.MonthBegin(11)
chains = con.execute('''
WITH t12 AS (SELECT item_no, SUM(sales_bottles) AS b12, SUM(sales_dollars) AS d12
             FROM sales WHERE order_date BETWEEN ? AND ? AND sales_bottles > 0 GROUP BY 1),
alltime AS (SELECT item_no, SUM(sales_bottles) AS b_all FROM sales WHERE sales_bottles > 0 GROUP BY 1),
m AS (SELECT s.*, COALESCE(t.b12, 0) AS b12, COALESCE(t.d12, 0) AS d12, COALESCE(a.b_all, 0) AS b_all
      FROM item_series s LEFT JOIN t12 t USING (item_no) LEFT JOIN alltime a USING (item_no))
SELECT series_id, COUNT(*) AS item_numbers, MIN(d) AS description, MIN(ml) AS ml,
       string_agg(item_no || ' (' || strftime(first_order, '%Y-%m') || ' to ' || strftime(last_order, '%Y-%m') || ')', ' > '
                  ORDER BY first_order) AS chain,
       SUM(d12) AS dollars_t12, SUM(b12) AS bottles_t12,
       SUM(CASE WHEN item_no <> series_id THEN b12 ELSE 0 END) AS bottles_t12_moved,
       SUM(CASE WHEN item_no <> series_id THEN b_all ELSE 0 END) AS bottles_all_moved,
       BOOL_OR(link_category_differs) AS category_differs,
       SUM(CASE WHEN link_kind = 'overlap' THEN 1 ELSE 0 END) AS overlap_links,
       SUM(CASE WHEN link_kind = 'gap' THEN 1 ELSE 0 END) AS gap_links,
       SUM(CASE WHEN link_kind = 'overlap' THEN b12 ELSE 0 END) AS bottles_t12_moved_overlap,
       SUM(CASE WHEN link_kind = 'gap' THEN b12 ELSE 0 END) AS bottles_t12_moved_gap
FROM m GROUP BY series_id HAVING COUNT(*) > 1 ORDER BY dollars_t12 DESC''', [T12_START.date(), T12_END.date()]).df()
chains.to_csv(OUT / "series_chains.csv", index=False)
chains.head(30).to_csv(OUT / "series_chains_top30_for_hand_check.csv", index=False)
tot = con.execute("SELECT SUM(sales_bottles) FROM sales WHERE order_date BETWEEN ? AND ? AND sales_bottles > 0",
                  [T12_START.date(), T12_END.date()]).fetchone()[0]
print(f"items {len(item_series):,} | series {item_series.series_id.nunique():,} | links {int(item_series.predecessor.notna().sum()):,} "
      f"| chains {len(chains):,} | links with a different category {int(item_series.link_category_differs.sum()):,}")
print(f"bottles moved onto an older series id: trailing 12 months {chains.bottles_t12_moved.sum():,.0f} "
      f"({100 * chains.bottles_t12_moved.sum() / tot:.2f}% of trailing-12 bottles); all time {chains.bottles_all_moved.sum():,.0f}")
for k in ["overlap", "gap"]:
    print(f"  {k} links: {int((item_series.link_kind == k).sum()):,}; trailing-12 bottles moved "
          f"{chains[f'bottles_t12_moved_{k}'].sum():,.0f} ({100 * chains[f'bottles_t12_moved_{k}'].sum() / tot:.2f}%)")
# ambiguous candidate pairs (not linked): with trailing-12 dollars, so the ones that matter can be decided by hand
d12 = con.execute('''SELECT item_no, SUM(sales_dollars) AS d12 FROM sales WHERE order_date BETWEEN ? AND ?
                     AND sales_bottles > 0 GROUP BY 1''', [T12_START.date(), T12_END.date()]).df().set_index("item_no").d12
ambiguous["newer_dollars_t12"] = ambiguous.newer.map(d12).fillna(0)
ambiguous["older_dollars_t12"] = ambiguous.older.map(d12).fillna(0)
ambiguous["description"] = ambiguous.newer.map(item_series.set_index("item_no").d)
ambiguous["ml"] = ambiguous.newer.map(item_series.set_index("item_no").ml)
ambiguous = ambiguous.sort_values(["newer_dollars_t12", "newer"], ascending=[False, True])
ambiguous.to_csv(OUT / "ambiguous_links.csv", index=False)
amb_new = ambiguous.newer.nunique()
print(f"ambiguous (not one to one, left unlinked): {len(ambiguous):,} candidate pairs on {amb_new:,} newer numbers; "
      f"trailing-12 dollars on those newer numbers {ambiguous.drop_duplicates('newer').newer_dollars_t12.sum():,.0f}")
# decision 46 reports: links the price guard removed (one to one without it, not made with it), and edge candidates
removed_links["newer_bottles_t12"] = removed_links.newer.map(con.execute('''SELECT item_no, SUM(sales_bottles) AS b
    FROM sales WHERE order_date BETWEEN ? AND ? AND sales_bottles > 0 GROUP BY 1''',
    [T12_START.date(), T12_END.date()]).df().set_index("item_no").b).fillna(0)
removed_links["newer_dollars_t12"] = removed_links.newer.map(d12).fillna(0)
removed_links["description"] = removed_links.newer.map(item_series.set_index("item_no").d)
removed_links.sort_values("newer_dollars_t12", ascending=False).to_csv(OUT / "links_removed_by_price_guard.csv", index=False)
edges = cand_all[cand_all.price_ratio.between(0.5, 0.67, inclusive="left") | (cand_all.price_ratio > 1.5) & (cand_all.price_ratio <= 2.0)].copy()
edges["description"] = edges.newer.map(item_series.set_index("item_no").d)
edges["newer_dollars_t12"] = edges.newer.map(d12).fillna(0)
edges.sort_values("newer_dollars_t12", ascending=False).to_csv(OUT / "price_ratio_edge_candidates.csv", index=False)
print(f"price guard (decision 46, band {PRICE_BAND}): links removed {len(removed_links):,}; their trailing-12 bottles "
      f"{removed_links.newer_bottles_t12.sum():,.0f} ({100 * removed_links.newer_bottles_t12.sum() / tot:.2f}%); "
      f"links with under 3 months of orders on a side (flagged) {int(item_series.link_price_thin.sum())}; "
      f"edge candidates (ratio 0.5-0.67 or 1.5-2.0) {len(edges)}")
# Addendum 4 (d): newer numbers with a candidate older number (same description and size, +-90 days) left unlinked
b12 = con.execute('''SELECT item_no, SUM(sales_bottles) AS b FROM sales WHERE order_date BETWEEN ? AND ?
                     AND sales_bottles > 0 GROUP BY 1''', [T12_START.date(), T12_END.date()]).df().set_index("item_no").b
linked_new = set(item_series.loc[item_series.predecessor.notna(), "item_no"])
un = cand_all[~cand_all.newer.isin(linked_new)].groupby("newer").agg(one_to_one=("one_to_one", "max")).reset_index()
un["b12"] = un.newer.map(b12).fillna(0)
print(f"candidates left unlinked (trailing-12 bottles on the newer number): not one to one "
      f"{un.loc[~un.one_to_one, 'b12'].sum():,.0f} ({100 * un.loc[~un.one_to_one, 'b12'].sum() / tot:.2f}%), "
      f"removed by the price guard {un.loc[un.one_to_one, 'b12'].sum():,.0f} ({100 * un.loc[un.one_to_one, 'b12'].sum() / tot:.2f}%); "
      f"linked {chains.bottles_t12_moved.sum():,.0f} ({100 * chains.bottles_t12_moved.sum() / tot:.2f}%)")
display(chains.head(10))
""")

md(r"""
### 9g-2. Carrier check (decision 47): numbers whose price per ml is far above their siblings'
**What:** for every item number that shares its description and bottle size with at least one other number, dollars
per ml (median dollars per bottle over its last 12 months with orders ÷ bottle size) against the median of the other
numbers in that group. Numbers at 3x or more are listed as likely multi-unit carriers (a pack counted as one bottle),
with their share of trailing-12-month dollars and bottles, and the state's liters column against bottles × size on
their rows. Nothing is corrected here; the design thread rules after seeing the size.
**Why:** a carrier understates bottles and volume (bottles × ml), so it matters beyond linking.
""")
code(r"""
ia = items_attr.copy()
ia["usd_per_ml"] = ia.price_last12 / ia.ml
grp = ia.groupby(["d", "ml"])
ia["n_in_group"] = grp.item_no.transform("size")
def med_others(g):
    v = g.usd_per_ml.to_numpy()
    return pd.Series([np.nanmedian(np.delete(v, i)) if len(v) > 1 else np.nan for i in range(len(v))], index=g.index)
ia["others_median_usd_per_ml"] = grp.apply(med_others, include_groups=False).reset_index(level=[0, 1], drop=True)
ia["ratio_to_others"] = ia.usd_per_ml / ia.others_median_usd_per_ml
carriers = ia[(ia.n_in_group > 1) & (ia.ratio_to_others >= 3)].copy()
con.register("carr", carriers[["item_no"]])
cs = con.execute('''
SELECT item_no, SUM(CASE WHEN order_date BETWEEN ? AND ? THEN sales_dollars ELSE 0 END) AS dollars_t12,
       SUM(CASE WHEN order_date BETWEEN ? AND ? THEN sales_bottles ELSE 0 END) AS bottles_t12,
       SUM(sales_liters_raw) AS state_liters, SUM(sales_bottles * bottle_volume_ml / 1000.0) AS bottles_x_ml_liters,
       arg_max(vendor_name, order_date) AS vendor, MODE(pack) AS pack
FROM sales WHERE sales_bottles > 0 AND item_no IN (SELECT item_no FROM carr) GROUP BY 1''',
    [T12_START.date(), T12_END.date()] * 2).df()
carriers = carriers.merge(cs, on="item_no", how="left").sort_values("dollars_t12", ascending=False)
carriers["state_liters_over_bottles_x_ml"] = carriers.state_liters / carriers.bottles_x_ml_liters
carriers.to_csv(OUT / "carriers_decision47.csv", index=False)
tot_d = con.execute("SELECT SUM(sales_dollars) FROM sales WHERE order_date BETWEEN ? AND ? AND sales_bottles > 0",
                    [T12_START.date(), T12_END.date()]).fetchone()[0]
top_v = con.execute('''SELECT vendor_name FROM sales WHERE order_date BETWEEN ? AND ? GROUP BY 1
                        ORDER BY SUM(sales_dollars) DESC LIMIT 20''', [T12_START.date(), T12_END.date()]).df().vendor_name
CARRIER_PCT_DOLLARS = 100 * carriers.dollars_t12.sum() / tot_d
print(f"carriers (decision 47, dollars per ml >= 3x the other numbers with the same description and size): "
      f"{len(carriers):,} numbers; trailing-12 dollars {carriers.dollars_t12.sum():,.0f} ({CARRIER_PCT_DOLLARS:.2f}%), "
      f"bottles {carriers.bottles_t12.sum():,.0f} ({100 * carriers.bottles_t12.sum() / tot:.2f}%)")
print(f"carrier rows: state liters / (bottles x ml) = {carriers.state_liters.sum() / carriers.bottles_x_ml_liters.sum():.3f} "
      f"(median per item {carriers.state_liters_over_bottles_x_ml.median():.3f}); "
      f"carriers with a trailing-12 order from a top-20 vendor by dollars: {int((carriers.dollars_t12 > 0).mul(carriers.vendor.isin(top_v)).sum())}")
display(carriers.head(15)[["item_no", "d", "ml", "pack", "vendor", "price_last12", "ratio_to_others", "dollars_t12",
                           "bottles_t12", "state_liters_over_bottles_x_ml"]].round(2))

# Addendum 4 (c): second test from the state's liters. On rows where sales_liters has decimals (not truncated), the
# ratio sales_liters / (bottles x ml / 1000) per item; a carrier is an item whose ratios sit on one whole multiple k >= 2
# (median ratio within 0.05 of k, and at least 80% of its decimal rows within 5% of k). k is the units per carrier.
# The 0.05 / 5% / 80% cut-offs are my operational reading of "consistent", reported as such.
lt = con.execute('''
WITH r AS (SELECT item_no, sales_liters_raw / (sales_bottles * bottle_volume_ml / 1000.0) AS ratio
           FROM sales WHERE sales_bottles > 0 AND bottle_volume_ml > 0 AND sales_liters_raw IS NOT NULL
             AND sales_liters_raw <> floor(sales_liters_raw)),
m AS (SELECT item_no, COUNT(*) AS decimal_rows, MEDIAN(ratio) AS med_ratio FROM r GROUP BY 1)
SELECT m.item_no, m.decimal_rows, m.med_ratio, round(m.med_ratio) AS k,
       AVG(CASE WHEN abs(r.ratio - round(m.med_ratio)) <= 0.05 * round(m.med_ratio) THEN 1.0 ELSE 0.0 END) AS share_on_k
FROM m JOIN r USING (item_no) GROUP BY 1, 2, 3, 4''').df()
lt["liters_carrier"] = (lt.k >= 2) & ((lt.med_ratio - lt.k).abs() <= 0.05) & (lt.share_on_k >= 0.8)
both = pd.DataFrame({"item_no": pd.concat([carriers.item_no, lt.loc[lt.liters_carrier, "item_no"]]).unique()})
both["sibling_test"] = both.item_no.isin(carriers.item_no)
both = both.merge(lt[["item_no", "decimal_rows", "med_ratio", "k", "share_on_k", "liters_carrier"]], on="item_no", how="left")
both["liters_carrier"] = both.liters_carrier.fillna(False).astype(bool)
both["tests_agree"] = both.sibling_test == both.liters_carrier
both["no_decimal_rows"] = both.decimal_rows.isna()
both = both.merge(ia[["item_no", "d", "ml", "ratio_to_others"]], on="item_no", how="left")
both.to_csv(OUT / "carrier_units_tests.csv", index=False)
print(f"liters test: {int(lt.liters_carrier.sum()):,} carriers (k: {lt.loc[lt.liters_carrier, 'k'].value_counts().head(6).to_dict()}); "
      f"sibling test {len(carriers):,}; both {int((both.sibling_test & both.liters_carrier).sum())}, "
      f"sibling only {int((both.sibling_test & ~both.liters_carrier).sum())} (of which no decimal liters rows "
      f"{int((both.sibling_test & both.no_decimal_rows).sum())}), liters only {int((~both.sibling_test & both.liters_carrier).sum())}")
# corrected liters (bottles x k x ml) against bottles x ml, trailing 12 months, statewide and by vendor (the brand map is
# not built yet; brand-level rows follow when it is)
con.register("kmap", lt.loc[lt.liters_carrier, ["item_no", "k"]])
cl = con.execute('''
SELECT vendor_name, SUM(sales_bottles * bottle_volume_ml) / 1e3 AS liters_bottles_x_ml,
       SUM(sales_bottles * bottle_volume_ml * COALESCE(k.k, 1)) / 1e3 AS liters_corrected
FROM sales s LEFT JOIN kmap k USING (item_no)
WHERE order_date BETWEEN ? AND ? AND sales_bottles > 0 GROUP BY 1''', [T12_START.date(), T12_END.date()]).df()
st = cl[["liters_bottles_x_ml", "liters_corrected"]].sum()
cl["pct_diff"] = 100 * (cl.liters_corrected / cl.liters_bottles_x_ml - 1)
cl = cl.sort_values("liters_bottles_x_ml", ascending=False)
cl.to_csv(OUT / "carrier_liters_correction_by_vendor.csv", index=False)
print(f"trailing-12 liters: bottles x ml {st.liters_bottles_x_ml:,.0f} | corrected {st.liters_corrected:,.0f} "
      f"({100 * (st.liters_corrected / st.liters_bottles_x_ml - 1):+.2f}% statewide); top-20 vendors by liters, largest "
      f"differences: {cl.head(20).sort_values('pct_diff', ascending=False).head(3)[['vendor_name', 'pct_diff']].round(2).values.tolist()}")
""")

md(r"""
## 9h. Monthly table per linked series, and the classes at the last origin
**What:** `series_month` is `product_month` summed over the item numbers of each series, on a grid from the series'
first order month to the last data month. The demand classes at the last origin are then recomputed per series.
**Why:** stage 2 forecasts, scores and builds the brand map on `series_id` (decision 42); `product_month` stays as the
item-level record.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE series_month AS
WITH sm AS (
    SELECT s.series_id, p.month_start, SUM(p.bottles) AS bottles, SUM(p.liters) AS liters, SUM(p.cases_9l) AS cases_9l,
           SUM(p.physical_cases) AS physical_cases, SUM(p.dollars_retail) AS dollars_retail,
           MAX(p.calendar_order_days) AS calendar_order_days, BOOL_AND(p.month_complete) AS month_complete
    FROM product_month p JOIN item_series s USING (item_no)
    GROUP BY 1, 2
)
SELECT *, CASE WHEN bottles > 0 THEN dollars_retail / bottles END AS avg_price_paid_per_bottle
FROM sm
''')
chk = con.execute('''SELECT (SELECT SUM(bottles) FROM product_month) AS item_bottles, (SELECT SUM(bottles) FROM series_month) AS series_bottles,
                            (SELECT COUNT(DISTINCT series_id) FROM series_month) AS series,
                            (SELECT COUNT(*) FROM series_month) AS series_months''').df()
display(chk)
assert np.isclose(chk.item_bottles[0], chk.series_bottles[0], rtol=0, atol=1e-6)   # restated bottles are fractional: float sums
con.execute(f"COPY series_month TO '{(OUT / 'series_month.parquet').as_posix()}' (FORMAT PARQUET)")

def series_class_counts(origin):
    o = pd.Timestamp(origin)
    w0, w1 = (o - pd.DateOffset(months=23)).strftime("%Y-%m-%d"), o.strftime("%Y-%m-%d")
    a0 = (o - pd.DateOffset(months=11)).strftime("%Y-%m-%d")
    return con.execute(f'''
    WITH active AS (SELECT DISTINCT series_id FROM series_month
                    WHERE month_start BETWEEN DATE '{a0}' AND DATE '{w1}' AND bottles > 0),
    first AS (SELECT series_id, MIN(month_start) AS first_m FROM series_month WHERE bottles > 0 GROUP BY 1),
    s AS (
        SELECT p.series_id, COUNT(*) AS n_months,
               SUM(CASE WHEN bottles > 0 THEN 1 ELSE 0 END) AS nz,
               AVG(CASE WHEN bottles > 0 THEN bottles END) AS mean_size,
               STDDEV_SAMP(CASE WHEN bottles > 0 THEN bottles END) AS sd_size,
               SUM(bottles) AS total_bottles, SUM(dollars_retail) AS dollars
        FROM series_month p JOIN active USING (series_id)
        WHERE p.month_start BETWEEN DATE '{w0}' AND DATE '{w1}'
        GROUP BY p.series_id
    )
    SELECT s.*, date_diff('month', f.first_m, DATE '{w1}') + 1 AS months_since_first,
           n_months * 1.0 / NULLIF(nz, 0) AS adi, POWER(sd_size / mean_size, 2) AS cv2,
           CASE WHEN date_diff('month', f.first_m, DATE '{w1}') + 1 < 12 THEN 'new'
                WHEN nz < 2 THEN 'intermittent'
                WHEN n_months * 1.0 / nz <= 1.32 AND POWER(COALESCE(sd_size, 0) / mean_size, 2) < 0.49 THEN 'smooth'
                WHEN n_months * 1.0 / nz <= 1.32 THEN 'erratic'
                WHEN POWER(COALESCE(sd_size, 0) / mean_size, 2) < 0.49 THEN 'intermittent'
                ELSE 'lumpy' END AS demand_class
    FROM s JOIN first f USING (series_id)''').df()

cls_s = series_class_counts(LAST_COMPLETE_MONTH)
cls_s.to_csv(OUT / "series_classes_last_origin.csv", index=False)
summary_s = cls_s.groupby("demand_class").agg(series=("series_id", "size"), dollars=("dollars", "sum"), bottles=("total_bottles", "sum"))
summary_s["pct_dollars"] = (100 * summary_s.dollars / summary_s.dollars.sum()).round(1)
print("series classes at the last origin (protocol 1.3 section 6: new = under 12 months since first order; "
      "intermittent also when under 2 non-zero months; ADI cut 1.32, CV2 cut 0.49):")
display(summary_s)
""")

md(r"""
## 10. Weekly SBC demand classes (side table; the monthly classes in 9f are the ones the models use)
**What:** for each item, two numbers and a class.
- **ADI** (average demand interval) = weeks in the item's history ÷ weeks with demand. ADI = 1 means it sells every week;
  ADI = 4 means about one week in four.
- **CV²** = squared coefficient of variation of the *non-zero* weekly quantities (how much order size varies when it does sell).

Cut-offs from Syntetos, Boylan & Croston (2005, *Journal of the Operational Research Society* 56(5), 495-503):

| | CV² < 0.49 | CV² ≥ 0.49 |
|---|---|---|
| **ADI < 1.32** | smooth | erratic |
| **ADI ≥ 1.32** | intermittent | lumpy |

**Why:** the cut-offs come from the paper's comparison of Croston's method, SBA and simple exponential smoothing;
they mark where each method's expected error is lowest, so the class tells stage 2 which model family to start from.
CV² uses the sample standard deviation (as in Kourentzes' `tsintermittent` R package); an item with fewer than
2 demand weeks has no CV², so it gets its own label instead of a guessed class.
**Window:** classes use only `CLASS_START` to `CLASS_END` (2024-2025, 104 weeks), recent enough to describe today's
demand and entirely before the frozen test period. An item's history inside the window starts at its first demand week.
Two more labels keep dead items out of the four classes: **no demand in window** (not ordered at all in 2024-2025) and
**inactive** (no orders in the last 26 weeks of the window, so probably discontinued; its trailing zeros would
otherwise inflate ADI).
""")
code(r"""
ADI_CUT, CV2_CUT, MIN_DEMANDS = 1.32, 0.49, 2

def q_sbc(d):
    T = d["table"]
    return f'''
    WITH s AS (
        SELECT item_no,
               COUNT(*)                                         AS n_weeks,
               SUM(CASE WHEN bottles > 0 THEN 1 ELSE 0 END)     AS n_demand_weeks,
               SUM(bottles)                                     AS total_bottles,
               AVG(CASE WHEN bottles > 0 THEN bottles END)          AS mean_size,
               STDDEV_SAMP(CASE WHEN bottles > 0 THEN bottles END)  AS sd_size,
               MAX(CASE WHEN bottles > 0 THEN week_start END)   AS last_demand_week
        FROM {T('weekly_demand')}
        WHERE week_start BETWEEN DATE '{CLASS_START}' AND DATE '{CLASS_END}'
        GROUP BY item_no
    )
    SELECT *,
           n_weeks * 1.0 / NULLIF(n_demand_weeks, 0)           AS adi,
           POWER(sd_size / mean_size, 2)                       AS cv2,
           CASE
             WHEN n_demand_weeks = 0 THEN 'no demand in window'
             WHEN last_demand_week < {d["add_days"](f"DATE '{CLASS_END}'", -26 * 7)} THEN 'inactive'
             WHEN n_demand_weeks < {MIN_DEMANDS} THEN 'too few demands'
             WHEN n_weeks * 1.0 / n_demand_weeks <  {ADI_CUT} AND POWER(sd_size / mean_size, 2) <  {CV2_CUT} THEN 'smooth'
             WHEN n_weeks * 1.0 / n_demand_weeks <  {ADI_CUT} THEN 'erratic'
             WHEN POWER(sd_size / mean_size, 2) <  {CV2_CUT}                            THEN 'intermittent'
             ELSE 'lumpy'
           END AS sbc_class
    FROM s
    '''
run("item_sbc", q_sbc)
con.execute('''
SELECT sbc_class, COUNT(*) AS items, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_items,
       ROUND(100.0 * SUM(total_bottles) / SUM(SUM(total_bottles)) OVER (), 1) AS pct_bottles
FROM item_sbc GROUP BY sbc_class ORDER BY items DESC''').df()
""")

md(r"""
## 11. ABC classes by spend
**What:** ranks items by spend in the class window (sales_dollars, what stores paid the state, 2024-2025) and cuts the running total at
80% (A) and 95% (B); the rest is C.
**Why:** ABC tells the planner where the money is, so attention and the most careful checks go to
the few items that carry most of the inventory dollars (Silver, Pyke & Thomas, *Inventory and Production
Management in Supply Chains*, 4th ed., 2017, ch. 2). The 80/95 cut-offs are a common convention, not a law; the
cell shows how concentrated spend really is so we can judge whether they fit.
An item is A if the running total **before** it is under 80%, so the item that crosses the line counts as A.
""")
code(r"""
A_CUT, B_CUT = 0.80, 0.95

def q_abc(d):
    T = d["table"]
    return f'''
    WITH spend AS (
        SELECT item_no, SUM(dollars) AS spend FROM {T('weekly_demand')}
        WHERE week_start BETWEEN DATE '{CLASS_START}' AND DATE '{CLASS_END}'
        GROUP BY item_no HAVING SUM(dollars) > 0
    ),
    ranked AS (
        SELECT item_no, spend,
               SUM(spend) OVER (ORDER BY spend DESC, item_no ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                 / SUM(spend) OVER () AS cum_share,
               spend / SUM(spend) OVER () AS share
        FROM spend
    )
    SELECT item_no, spend, share, cum_share,
           CASE WHEN cum_share - share < {A_CUT} THEN 'A'
                WHEN cum_share - share < {B_CUT} THEN 'B'
                ELSE 'C' END AS abc_class
    FROM ranked
    '''
run("item_abc", q_abc)
con.execute('''
SELECT abc_class, COUNT(*) AS items, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_items,
       ROUND(SUM(spend) / 1e6, 2) AS spend_musd, ROUND(100.0 * SUM(share), 1) AS pct_spend
FROM item_abc GROUP BY abc_class ORDER BY abc_class''').df()
""")

md(r"""
## 12. ABC × SBC grid and the item table
**What:** joins the two classifications and counts items and spend in each cell, then saves the item table.
**Why:** this grid is the brief for stage 2. For example, "A-smooth" items get the full model ensemble and tight
service targets; "C-lumpy" items get a simple intermittent method and a lower target. The saved
`item_classes.csv` and `weekly_demand.parquet` are the inputs to the forecasting stage.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE item_classes AS
WITH attrs AS (   -- most common description / vendor / category per item
    SELECT item_no, im_desc, vendor_name, category_name,
           ROW_NUMBER() OVER (PARTITION BY item_no ORDER BY COUNT(*) DESC, im_desc) AS rn
    FROM sales GROUP BY item_no, im_desc, vendor_name, category_name
)
SELECT s.item_no, a.im_desc, v.current_vendor_number, v.current_vendor_name, v.vendors_over_time, a.category_name,
       s.n_weeks, s.n_demand_weeks, s.total_bottles, s.mean_size, s.adi, s.cv2, s.sbc_class,
       sm.adi AS adi_monthly, sm.cv2 AS cv2_monthly, sm.sbc_class_monthly,
       COALESCE(b.spend, 0) AS spend, b.share, b.cum_share, COALESCE(b.abc_class, '-') AS abc_class
FROM item_sbc s LEFT JOIN item_abc b ON b.item_no = s.item_no
LEFT JOIN attrs a ON a.item_no = s.item_no AND a.rn = 1
LEFT JOIN item_vendor v ON v.item_no = s.item_no
LEFT JOIN item_sbc_monthly sm ON sm.item_no = s.item_no
''')
grid_items = con.execute("PIVOT item_classes ON sbc_class USING COUNT(*) GROUP BY abc_class ORDER BY abc_class").df()
grid_spend = con.execute("PIVOT item_classes ON sbc_class USING ROUND(100 * SUM(share), 1) GROUP BY abc_class ORDER BY abc_class").df()
display(grid_items); display(grid_spend)

for t in ["weekly_demand", "product_month", "item_vendor"]:
    con.execute(f"COPY {t} TO '{(OUT / (t + '.parquet')).as_posix()}' (FORMAT PARQUET)")
con.execute("SELECT * FROM item_classes ORDER BY spend DESC").df().to_csv(OUT / "item_classes.csv", index=False)
print("saved:", sorted(p.name for p in OUT.iterdir()))
""")

md(r"""
## 12b. Reusable side tables for later analyses
**What:** two extra tables saved next to the main outputs.
- `product_dim`: one row per item and attribute *version* (description, vendor, pack, size, state cost and retail),
  with the first and last order date each version was seen, so price and pack changes stay visible.
- `item_county_week`: bottles and spend per item, county and week (orders only, no zero fill).

**Why:** later work on market share, assortment and supplier concentration needs product attributes and some
geography. Building them now from the same cleaned lines costs seconds and keeps every analysis on one definition
of demand. County rather than store keeps the table a manageable size.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE product_dim AS
SELECT item_no, im_desc, category_code, category_name, vendor_number, vendor_name,
       pack, bottle_volume_ml, state_bottle_cost, state_bottle_retail,
       MIN(order_date) AS first_order_date, MAX(order_date) AS last_order_date,
       COUNT(*) AS order_lines
FROM sales
GROUP BY ALL
ORDER BY item_no, first_order_date
''')
wk = DIALECTS["duckdb"]["week"]("order_date")
con.execute(f'''
CREATE OR REPLACE TABLE item_county_week AS
SELECT item_no, county_name, {wk} AS week_start,
       SUM(sales_bottles) AS bottles, SUM(sales_dollars) AS dollars
FROM sales
WHERE sales_bottles > 0 AND order_date IS NOT NULL
GROUP BY ALL
''')
con.execute(f"COPY product_dim TO '{(OUT / 'product_dim.parquet').as_posix()}' (FORMAT PARQUET)")
con.execute(f"COPY item_county_week TO '{(OUT / 'item_county_week.parquet').as_posix()}' (FORMAT PARQUET)")
con.execute('''
SELECT (SELECT COUNT(DISTINCT item_no) FROM product_dim) AS items,
       (SELECT COUNT(*) FROM product_dim)                AS item_versions,
       (SELECT COUNT(*) FROM item_county_week)           AS item_county_weeks
''').df()
""")

md(r"""
## 12c. Store tables for the store drill-down
**What:** `store_category_month` holds bottles, dollars, liters, order lines and the number of distinct order dates per
store, category and month. `store_dim` holds one row per store with its most common name, city and county, its first
and last order date, and how many different names and cities its store number has carried.
**Why:** the store view forecasts monthly demand per store and category (store by product would be millions of thin
series). Distinct order dates are kept because a store with 5 delivery days in a month orders more than one with 4,
for calendar reasons alone, so the model can adjust for it. Name and city counts above 1 flag a store number that may
have been reused or renamed, which matters before any store's history is read as one continuous series.
""")
code(r"""
con.execute('''
CREATE OR REPLACE TABLE store_category_month AS
SELECT store_no, category_name,
       CAST(date_trunc('month', order_date) AS DATE) AS month_start,
       SUM(sales_bottles)                AS bottles,
       SUM(sales_dollars)                AS dollars,
       SUM(sales_liters)                 AS liters,
       COUNT(*)                          AS order_lines,
       COUNT(DISTINCT order_date)        AS order_dates
FROM sales
WHERE sales_bottles > 0 AND order_date IS NOT NULL
GROUP BY ALL
''')
con.execute('''
CREATE OR REPLACE TABLE store_dim AS
WITH n AS (
    SELECT store_no, store_name, city, county_name, COUNT(*) AS lines,
           ROW_NUMBER() OVER (PARTITION BY store_no ORDER BY COUNT(*) DESC, store_name) AS rn
    FROM sales GROUP BY store_no, store_name, city, county_name
)
SELECT s.store_no, n.store_name, n.city, n.county_name,
       MIN(s.order_date) AS first_order_date, MAX(s.order_date) AS last_order_date,
       COUNT(DISTINCT s.store_name) AS names_seen, COUNT(DISTINCT s.city) AS cities_seen,
       COUNT(*) AS order_lines
FROM sales s JOIN n ON n.store_no = s.store_no AND n.rn = 1
GROUP BY s.store_no, n.store_name, n.city, n.county_name
''')
con.execute(f"COPY store_category_month TO '{(OUT / 'store_category_month.parquet').as_posix()}' (FORMAT PARQUET)")
con.execute(f"COPY store_dim TO '{(OUT / 'store_dim.parquet').as_posix()}' (FORMAT PARQUET)")
con.execute('''
SELECT COUNT(*) AS stores,
       SUM(CASE WHEN names_seen > 1 THEN 1 ELSE 0 END)  AS stores_with_several_names,
       SUM(CASE WHEN cities_seen > 1 THEN 1 ELSE 0 END) AS stores_with_several_cities,
       (SELECT COUNT(*) FROM store_category_month)      AS store_category_months
FROM store_dim
''').df()
""")

md(r"""
## 13. Independent check
**What:** `verify_stage1.py` rebuilds the weekly table, the SBC classes and the ABC classes from the raw CSVs
using pandas only (no SQL, no DuckDB), then compares them with the tables above.
**Why:** two separate implementations agreeing is much stronger evidence than one implementation looking reasonable.
""")
code(r"""
import subprocess, sys
r = subprocess.run([sys.executable, str(BASE / "verify_stage1.py"), str(BASE)], capture_output=True, text=True)
print(r.stdout, r.stderr[-3000:])
""")
code(r"""
con.close()
""")

nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3 (ds)", "language": "python"}
nbf.write(nb, sys.argv[1])
print("cells:", len(cells))
