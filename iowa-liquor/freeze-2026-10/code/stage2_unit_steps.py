"""Unit-step scan (Addendum 5 follow-up): months where an item's dollars per bottle jumps by 1.8x or more (or falls
below 1/1.8) against the 3 months before, while dollars per month run smoothly (bottles move inversely). That pattern
means the state changed what one recorded "bottle" is (e.g. a sleeve became a case of sleeves), which breaks the
bottle history even when the recorded size does not change. Read-only. Detail: stage2/unit_steps.csv.
Usage: python unit_steps.py <base>"""
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd

if __name__ == "__main__":
    base = Path(sys.argv[1]); out = base / "stage2"
    con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
    im = con.execute('''
        SELECT item_no, date_trunc('month', order_date)::DATE AS m, SUM(sales_bottles) AS b, SUM(sales_dollars) AS usd,
               MODE(bottle_volume_ml) AS ml
        FROM sales WHERE sales_bottles > 0 GROUP BY 1, 2 ORDER BY 1, 2''').df()
    t12 = con.execute('''SELECT item_no, SUM(sales_dollars) AS usd_t12, SUM(sales_bottles) AS b_t12 FROM sales
        WHERE sales_bottles > 0 AND order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH GROUP BY 1''').df()
    desc = con.execute("SELECT item_no, d, series_id FROM item_series").df()
    rows = []
    for it, g in im.groupby("item_no"):
        if len(g) < 4:
            continue
        b, u, m, ml = g.b.to_numpy(float), g.usd.to_numpy(float), g.m.to_numpy(), g.ml.to_numpy()
        p = u / b
        for i in range(1, len(g)):
            lo, hi = max(0, i - 3), min(len(g), i + 3)
            pb = u[lo:i].sum() / b[lo:i].sum(); pa = u[i:hi].sum() / b[i:hi].sum()
            r = pa / pb
            if 1 / 1.8 < r < 1.8:
                continue
            br = b[i:hi].mean() / b[lo:i].mean(); dr = u[i:hi].mean() / u[lo:i].mean()
            if not (0.5 <= dr <= 2):            # dollars must run smoothly through the step
                continue
            # keep only the sharpest month of a step (price before and after, single month on each side)
            if abs(np.log(p[i] / p[i - 1])) < np.log(1.6):
                continue
            rows.append(dict(item_no=it, month=str(pd.Timestamp(m[i]).date()), price_before=pb, price_after=pa,
                             price_ratio=r, bottles_ratio=br, dollars_ratio=dr, ml_before=ml[i - 1], ml_after=ml[i],
                             near_whole=bool(abs(max(r, 1 / r) - round(max(r, 1 / r))) <= 0.1)))
    st = pd.DataFrame(rows)
    if len(st):
        st = st.merge(desc, on="item_no", how="left").merge(t12, on="item_no", how="left").fillna({"usd_t12": 0})
        st = st.sort_values("usd_t12", ascending=False)
    st.to_csv(out / "unit_steps.csv", index=False)
    print(f"unit steps (price x>=1.8 or <=1/1.8, dollars smooth): {len(st)} steps on {st.item_no.nunique() if len(st) else 0} items; "
          f"near a whole multiple: {int(st.near_whole.sum()) if len(st) else 0}; items with trailing-12 sales: "
          f"{st[st.usd_t12 > 0].item_no.nunique() if len(st) else 0} (${st.drop_duplicates('item_no').usd_t12.sum() if len(st) else 0:,.0f})")
    if len(st):
        print("item|month|price_before|price_after|ratio|bottles_ratio|ml|usd_t12|desc")
        for r in st.head(40).itertuples():
            print(f"{r.item_no}|{r.month}|{r.price_before:.2f}|{r.price_after:.2f}|{r.price_ratio:.2f}|{r.bottles_ratio:.2f}|"
                  f"{r.ml_before:g}>{r.ml_after:g}|{r.usd_t12:.0f}|{str(r.d)[:40]}")
