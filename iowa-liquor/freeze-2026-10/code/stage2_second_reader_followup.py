"""01e second-reader follow-up (ruling-01d C and amendment items 3-4). Read-only.
Usage: python second_reader_followup.py <base> <out.md>"""
import os; os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
base, outf = Path(sys.argv[1]), Path(sys.argv[2])
con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
tab = pd.read_csv(base / "stage1" / "unit_breaks.csv", dtype={"item_no": str, "month": str})
sel = tab[(tab.proposed_action == "restate") & (tab.usd_t12 > 50000)].sort_values("usd_t12", ascending=False)
items = sel.item_no.tolist()
lt = pd.read_csv(base / "stage2" / "units_table.csv", dtype={"item_no": str, "series_id": str})
st = pd.read_csv(base / "stage2" / "units_series_t12.csv", dtype={"series_id": str})
L = []; w = L.append
def raw_months(it, a, b):
    return con.execute('''SELECT strftime(date_trunc('month', order_date), '%Y-%m') AS m, SUM(sales_bottles_recorded) AS b,
        SUM(sales_dollars) AS usd, string_agg(DISTINCT CAST(pack AS VARCHAR), '/') AS packs, COUNT(*) AS lines
        FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles_recorded > 0 AND order_date >= ? AND order_date < ?
        GROUP BY 1 ORDER BY 1''', [it, a, b]).df()
w("# 01e second-reader follow-up (ruling 01d C, amendment items 3-4)")
w(""); w("Local Claude Code session, Nov 27-28 2026 PT. Raw figures are the state's (recorded bottles, dollars as kept or "
        "repaired by decision 32). Restated units only where a section says so.")

w(""); w("## 1. 84161 99 Blackberries mini: every month before 2024-10, and why it is cut, not restated"); w("")
x = raw_months("84161", "2000-01-01", "2024-10-01")
w("| month | raw bottles | dollars | $ per raw bottle | packs | lines |"); w("|---|---:|---:|---:|---|---:|")
for r in x.itertuples():
    w(f"| {r.m} | {r.b:,.0f} | {r.usd:,.2f} | {r.usd / r.b:.2f} | {r.packs} | {r.lines} |")
w(""); w("Orders stop in 2013 and resume in Oct 2024 at pack 1 and $78.60. The rule's before-median must come from months "
         "within 12 calendar months of the break (decision 62), and there are none, so the rule does not confirm it. The "
         "ruled restatement (1/10) then meets the continuity test on the 2012-13 months, which fails on the 11-year gap "
         "(restated units after / before 11.8, outside 0.5-2). A failing item is not restated; its series starts at the break, "
         "and the second reader could not tell, so nothing is restated on an uncertain reading (final action `cut`).")

w(""); w("## 2. The same season a year before the change: raw May-Oct 2022, and mean restated units per month"); w("")
w("| item | May-Oct 2022 raw bottles by month | $ per raw bottle | mean restated units / month, May-Oct 2022 | 2023 (window months out) | 2024 |")
w("|---|---|---:|---:|---:|---:|")
for it in items:
    r22 = raw_months(it, "2022-05-01", "2022-11-01")
    br = tab[(tab.item_no == it) & (tab.proposed_action == "restate")].month.iat[0]
    win = {br, (pd.Period(br, freq="M") + 1).strftime("%Y-%m")}
    mu = {}
    for y in (2022, 2023, 2024):
        q = con.execute('''SELECT strftime(date_trunc('month', order_date), '%Y-%m') AS m, SUM(sales_bottles) AS rb FROM sales
            WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles > 0 AND order_date >= ? AND order_date < ? GROUP BY 1''',
            [it, f"{y}-05-01", f"{y}-11-01"]).df()
        q = q[~q.m.isin(win)] if y == 2023 else q
        mu[y] = q.rb.mean() if len(q) else np.nan
    p = (r22.usd.sum() / r22.b.sum()) if len(r22) else np.nan
    w(f"| {it} | {', '.join(f'{v:,.0f}' for v in r22.b) if len(r22) else 'no orders'} | {p:.2f} | {mu[2022]:,.1f} | {mu[2023]:,.1f} | {mu[2024]:,.1f} |")

w(""); w("## 3. Tito's 38449, Nov 2025: the lines below $15.75"); w("")
t = con.execute('''SELECT ROUND(sales_dollars / sales_bottles_recorded, 2) AS p, pack, COUNT(*) AS lines, COUNT(DISTINCT store_no) AS stores,
        SUM(sales_bottles_recorded) AS bottles, string_agg(DISTINCT dollars_source, '; ') AS dollars_source,
        string_agg(DISTINCT CAST(state_bottle_retail_raw AS VARCHAR), '/') AS retail_raw, string_agg(DISTINCT CAST(state_bottle_retail AS VARCHAR), '/') AS retail_used,
        MIN(order_date) AS first, MAX(order_date) AS last
        FROM sales WHERE item_no = '38449' AND order_date >= DATE '2025-11-01' AND order_date < DATE '2025-12-01' AND sales_bottles_recorded > 0
        GROUP BY 1, 2 ORDER BY 1''').df()
w("| $ per bottle | pack | lines | stores | bottles | dollars source | state retail (raw) | retail used | first | last |")
w("|---:|---:|---:|---:|---:|---|---|---|---|---|")
for r in t.itertuples():
    w(f"| {r.p:.2f} | {r.pack} | {r.lines} | {r.stores} | {r.bottles:,.0f} | {r.dollars_source} | {r.retail_raw} | {r.retail_used} | {r.first:%Y-%m-%d} | {r.last:%Y-%m-%d} |")
sz = con.execute('''SELECT sales_bottles_recorded AS b, sales_dollars AS usd, COUNT(*) AS lines FROM sales
        WHERE item_no = '38449' AND order_date >= DATE '2025-11-01' AND order_date < DATE '2025-12-01' AND sales_bottles_recorded > 0
        GROUP BY 1, 2 ORDER BY 1''').df()
w(""); w("Line totals by bottles on the line (Nov 2025): " + "; ".join(f"{int(r.b)} btl -> ${r.usd:,.2f} ({r.lines} lines)" for r in sz.itertuples()))
w(""); w("Reading: every line is $15.75 a bottle. Nov 2025 is one of the three months in which every line carries a "
         "whole-number price and the state's line totals are cut to whole dollars (01c). 1 bottle is $15.75 cut to $15, "
         "2 bottles $31.50 cut to $31 ($15.50 each), 3 bottles $47.25 cut to $47 ($15.67 each); 4, 8 and 12 bottles come out "
         "whole. The item started in Nov 2025, so there is no cents price in the same month or within 3 months either side to "
         "repair the totals (decision 32 keeps the state's total); the loss is under $1 a line.")

w(""); w("## 4. Liters per current unit for the 15 items (amendment item 3: HELD until this is ruled)"); w("")
w("Price-implied figure: the new unit's price at the break (median line price in the after window) / $0.645 per mini "
  "(the reader's per-mini price), times 50 ml. The price has since risen to $81.00, so the break-month price is used. "
  "Tito's has no single-bottle reference price in its own history, so no implied figure is given.")
w(""); w("| item | recorded ml history (first - last month) | rule's tier before hold | rule's liters per current unit | price at break | price-implied minis | price-implied liters | agree? |")
w("|---|---|---|---:|---:|---:|---:|---|")
for it in items:
    h = con.execute('''SELECT bottle_volume_ml AS ml, strftime(MIN(order_date), '%Y-%m') AS a, strftime(MAX(order_date), '%Y-%m') AS b
        FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles_recorded > 0 GROUP BY 1 ORDER BY 2''', [it]).df()
    hist = "; ".join(f"{r.ml:g} ml ({r.a} - {r.b})" for r in h.itertuples())
    row = lt[(lt.item_no == it)].sort_values("last_order").tail(1)
    lpu = float(row.liters_per_unit.iat[0]) if len(row) else np.nan
    src = row.source.iat[0] if len(row) else ""
    ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str})
    cur = float(ap[ap.item_no == it].P1.iat[-1])          # new unit's price at the break (after-window median)
    if it == "38449":
        imp_n, imp_l = np.nan, np.nan
    else:
        imp_n = cur / 0.645; imp_l = imp_n * 0.05
    ok = "n/a" if np.isnan(imp_l) else ("yes" if abs(lpu / imp_l - 1) < 0.05 else "no")
    w(f"| {it} | {hist} | proven ({src}) | {lpu:.3f} L | ${cur:.2f} | {imp_n:,.0f} | {imp_l:.2f} L | {ok} |" if not np.isnan(imp_l) else
      f"| {it} | {hist} | proven ({src}) | {lpu:.3f} L | ${cur:.2f} | - | - | {ok} |")
w(""); w("Rule (decision 51): liters per current unit = recorded ml x size-history factor (rows at the smaller of a smooth "
         "whole-multiple size change take larger / smaller) x the unit-break pack (old pack / new pack). Where the rule "
         "and the price disagree, the item goes to the unknown tier and is left out of liters (amendment item 3), pending "
         "the ruling on this file.")
outf.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"01e follow-up: {len(items)} items -> {outf}")
