"""01d second-reader file (ruling-01b-amend item 4, amend2 layout). Read-only.
Part A: for every item with action `restate` in the frozen table and over $50,000 trailing-12 dollars, the state's RAW
figures for the 6 months each side of the break: raw bottles, dollars, dollars per raw bottle, recorded pack with line
counts, and for the break month and its neighbours the count of lines at each distinct price. No restated figures,
factors, actions or verdicts in Part A.
Part B (end of file): break month, factor, action, outcome and restated units per month for the same 12 months.
Usage: python second_reader.py <base> <out.md>"""
import sys
from pathlib import Path
import duckdb, pandas as pd
base, outf = Path(sys.argv[1]), Path(sys.argv[2])
con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
tab = pd.read_csv(base / "stage1" / "unit_breaks.csv", dtype={"item_no": str, "month": str})
app = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str}, parse_dates=["month"])
sel = tab[(tab.action == "restate") & (tab.usd_t12 > 50000)].sort_values("usd_t12", ascending=False)
A, B = [], []
for r in sel.itertuples():
    m0 = pd.Timestamp(r.month + "-01"); lo, hi = m0 - pd.DateOffset(months=6), m0 + pd.DateOffset(months=6)
    q = '''SELECT strftime(date_trunc('month', order_date), '%Y-%m') AS m, sales_bottles_recorded AS b, sales_bottles AS rb,
                  sales_dollars AS usd, pack, ROUND(sales_dollars / NULLIF(sales_bottles_recorded, 0), 2) AS p
           FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles_recorded > 0
             AND order_date >= ? AND order_date < ?'''
    x = con.execute(q, [r.item_no, lo.date(), hi.date()]).df()
    d = con.execute("SELECT MODE(im_desc), MODE(bottle_volume_ml) FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ?",
                    [r.item_no]).fetchone()
    A.append(f"\n### {r.item_no} {d[0]}, recorded size {d[1]:g} ml\n")
    A.append("| month | raw bottles | dollars | $ per raw bottle | recorded pack (lines) |")
    A.append("|---|---:|---:|---:|---|")
    for m, g in x.groupby("m"):
        packs = ", ".join(f"{int(k)} ({v})" for k, v in g.pack.value_counts().sort_index().items())
        A.append(f"| {m} | {g.b.sum():,.0f} | {g.usd.sum():,.2f} | {g.usd.sum() / g.b.sum():.2f} | {packs} |")
    near = [(m0 + pd.DateOffset(months=k)).strftime("%Y-%m") for k in (-1, 0, 1)]
    A.append("\nLines at each price, break month and the months beside it:\n")
    for m in near:
        g = x[x.m == m]
        if len(g):
            A.append(f"- {m}: " + "; ".join(f"${k:.2f} x {v} lines" for k, v in g.p.value_counts().sort_index().items()))
        else:
            A.append(f"- {m}: no orders")
    a = app[(app.item_no == r.item_no) & (app.month == m0)]
    oc = a.outcome.iat[0] if len(a) else "?"
    B.append(f"\n### {r.item_no}: break {r.month}, factor {r.factor:g} (new pack {r.pack_after} / old pack {r.pack_before}), "
             f"table action {r.action}, outcome {oc}\n")
    B.append("| month | restated units |"); B.append("|---|---:|")
    for m, g in x.groupby("m"):
        B.append(f"| {m} | {g.rb.sum():,.1f} |")
hdr = ["# 01d second reader: restated unit breaks above $50,000 trailing-12 dollars",
       "", f"Local Claude Code session, Nov 27 2026 PT. {len(sel)} items (frozen table action `restate`, trailing-12 over $50,000). "
       "Part A is the state's raw data only, so the reading can be made without the rule. Part B, at the end, shows what was applied.",
       "", "## Part A: the state's raw figures"]
tail = ["", "---", "", "## Applied by the rule (read Part A first)"]
outf.write_text("\n".join(hdr + A + tail + B) + "\n", encoding="utf-8")
print(f"second reader: {len(sel)} items -> {outf}")
