"""Addendum 8 data read, part 2 (read-only): for the top 100 series by trailing-12 dollars, every month where units
(restated bottles) or dollars per unit moved over 3x against the previous month with orders, with the line-level context
(recorded bottles, packs, line prices, item numbers) needed to read it by hand.
Usage: python top100_moves.py <base>  ->  stage1/top100_moves_over3x.txt"""
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
base = Path(sys.argv[1]); con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
sm = con.execute("SELECT series_id, month_start AS m, bottles, dollars_retail AS usd FROM series_month WHERE bottles > 0 ORDER BY 1, 2").df()
last = sm.m.max()
top = (sm[sm.m > last - pd.DateOffset(months=12)].groupby("series_id").usd.sum().sort_values(ascending=False).head(100))
x = sm[sm.series_id.isin(top.index)].copy()
x["p"] = x.usd / x.bottles
x["ur"] = x.groupby("series_id").bottles.transform(lambda v: v / v.shift())
x["pr"] = x.groupby("series_id").p.transform(lambda v: v / v.shift())
mv = x[(x.ur > 3) | (x.ur < 1 / 3) | (x.pr > 3) | (x.pr < 1 / 3)]
out = [f"top 100 series (trailing-12 ${top.sum():,.0f}); months with units or $/unit moving over 3x vs previous order month: "
       f"{len(mv)} on {mv.series_id.nunique()} series (units {int(((mv.ur > 3) | (mv.ur < 1/3)).sum())}, "
       f"price {int(((mv.pr > 3) | (mv.pr < 1/3)).sum())})"]
for r in mv.itertuples():
    d = con.execute("SELECT d FROM item_series WHERE item_no = ?", [r.series_id]).fetchone()[0]
    ctx = con.execute('''SELECT string_agg(DISTINCT s.item_no, '/') ids, string_agg(DISTINCT CAST(s.pack AS VARCHAR), '/') packs,
        SUM(s.sales_bottles_recorded) rec, string_agg(DISTINCT CAST(ROUND(s.sales_dollars / s.sales_bottles_recorded, 2) AS VARCHAR), '/') prices
        FROM sales s JOIN item_series i USING (item_no) WHERE i.series_id = ? AND s.sales_bottles > 0
          AND date_trunc('month', s.order_date) = ?''', [r.series_id, r.m]).fetchone()
    out.append(f"{r.series_id:>8} {str(d)[:32]:32} {r.m:%Y-%m} units {r.bottles:>9,.1f} (x{r.ur:.2f}) $/unit {r.p:>7.2f} (x{r.pr:.2f}) "
               f"| rec {ctx[2]:,.0f} pack {ctx[1]} items {ctx[0]} prices {str(ctx[3])[:40]}")
(base / "stage1" / "top100_moves_over3x.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print(out[0])
