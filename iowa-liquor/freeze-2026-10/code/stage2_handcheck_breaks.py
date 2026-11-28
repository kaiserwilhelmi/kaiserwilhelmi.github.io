"""Evidence for the unit-break hand checks (decisions 60-62, Addendum 8). Read-only on the database.
A: every applied break (confirmed or manual) on an item with trailing-12 sales, plus manual leave-alone entries.
B: second read, 20 applied breaks on items without trailing-12 sales (pool sorted by item and month, numpy seed 60).
C: hand-read list; pack changes left alone with trailing-12 sales over $10,000; unexplained price steps over $50,000;
   flagged items (ruling 01b item 5).
Each item shows recorded bottles, dollars, dollars per bottle, packs and line prices by month around its breaks.
Usage: python handcheck_breaks.py <base>   ->  stage1/unit_breaks_handcheck.txt, stage1/unit_breaks_second_read_sample.csv"""
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd

base = Path(sys.argv[1]); s1 = base / "stage1"
con = duckdb.connect(str(s1 / "iowa_liquor.duckdb"), read_only=True)
pc = pd.read_csv(s1 / "unit_pack_changes_all.csv", dtype={"item_no": str}, parse_dates=["month"])
us = pd.read_csv(s1 / "unexplained_steps.csv", dtype={"item_no": str}, parse_dates=["month"])
app = pc[pc.status.isin(["confirmed", "manual"])]
A = pd.concat([app[app.usd_t12 > 0], pc[pc.status == "leave_alone"]]).sort_values(["usd_t12", "month"], ascending=[False, True])
pool = app[app.usd_t12 == 0].sort_values(["item_no", "month"]).reset_index(drop=True)
B = pool.iloc[np.sort(np.random.default_rng(60).choice(len(pool), size=min(20, len(pool)), replace=False))]
B[["item_no", "month", "status", "outcome"]].to_csv(s1 / "unit_breaks_second_read_sample.csv", index=False)
FLAG = ["87035", "65933", "28081", "84172", "84160"]

t12 = con.execute('''SELECT regexp_replace(item_no, '~pre.*', '') AS item_no, SUM(sales_dollars) AS usd FROM sales
    WHERE sales_bottles > 0 AND order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH GROUP BY 1''').df().set_index("item_no").usd
out = []; w = out.append
def head(it):
    d = con.execute("SELECT MODE(im_desc), MODE(bottle_volume_ml) FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ?", [it]).fetchone()
    w(f"\n  {it}  {d[0]} ({d[1]:g} ml)  usd_t12 {t12.get(it, 0):,.0f}")
def months(it, a, b):
    g = con.execute(f"""SELECT strftime(date_trunc('month', order_date), '%Y-%m') m, SUM(sales_bottles_recorded) b,
        SUM(sales_bottles) rb, SUM(sales_dollars) usd, string_agg(DISTINCT CAST(pack AS VARCHAR), '/') packs,
        string_agg(DISTINCT CAST(ROUND(sales_dollars / sales_bottles_recorded, 2) AS VARCHAR), '/') prices,
        string_agg(DISTINCT item_no, '/') ids
        FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles_recorded > 0
          AND order_date >= ? AND order_date < ? GROUP BY 1 ORDER BY 1""", [it, a.date(), b.date()]).df()
    for r in g.itertuples():
        w(f"    {r.m}  btl {r.b:>7,.0f}  restated {r.rb:>8,.1f}  usd {r.usd:>9,.0f}  pack {r.packs:<7} prices {str(r.prices)[:48]:48} {r.ids}")
def brk(r):
    w(f"   {r.status:<12} {r.month:%Y-%m} pack {r.pack_old:g}->{r.pack_new:g}  P0 {r.P0:.2f} P1 {r.P1:.2f}  price/pack {r.price_over_pack:.2f}  "
      f"factor {r.factor:.4g}  months {r.months_before:g}/{r.months_after:g}  continuity units {r.units_after_over_before:.2f} "
      f"$ {r.price_after_over_before:.2f}  outcome {r.outcome}")
def block(df, title):
    w(f"\n{title}")
    for it, g in df.groupby("item_no", sort=False):
        head(it)
        for r in g.itertuples():
            brk(r)
        months(it, g.month.min() - pd.DateOffset(months=13), g.month.max() + pd.DateOffset(months=4))

block(A, f"A. Applied breaks on items with trailing-12 sales: {int((app.usd_t12 > 0).sum())} on {app[app.usd_t12 > 0].item_no.nunique()} items; "
         f"manual leave-alone entries: {int((pc.status == 'leave_alone').sum())}")
block(B, f"B. Second read: {len(B)} of {len(pool)} applied breaks on items without trailing-12 sales (seed 60)")
w(f"\nC1. Hand-read list (price/pack 0.67-0.8 or 1.25-1.5): {int((pc.status == 'hand_read').sum())}")
for r in pc[pc.status == "hand_read"].itertuples():
    w(f"   {r.item_no} {r.month:%Y-%m} pack {r.pack_old:g}->{r.pack_new:g} price/pack {r.price_over_pack:.2f} usd_t12 {r.usd_t12:,.0f}")
la = pc[pc.status.isin(["case_size", "no_prices_in_cap"]) & (pc.usd_t12 > 10000)]
w(f"\nC2. Pack changes of 1.8x+ left alone with trailing-12 sales over $10,000: {len(la)}")
for r in la.itertuples():
    w(f"   {r.item_no} {r.month:%Y-%m} {r.status} pack {r.pack_old:g}->{r.pack_new:g} price/pack {r.price_over_pack:.2f} usd_t12 {r.usd_t12:,.0f}")
big = us[us.usd_t12 > 50000]
block_items = big.drop_duplicates("item_no")
w(f"\nC3. Unexplained price steps (no break), items over $50,000 trailing-12: {len(big)} steps on {big.item_no.nunique()} items")
for r in big.itertuples():
    w(f"   {r.item_no} {r.month:%Y-%m} price {r.P0:.2f}->{r.P1:.2f} ratio {r.price_ratio:.2f} dollars ratio {r.dollars_ratio:.2f} "
      f"pack change nearby {r.pack_change_nearby} usd_t12 {r.usd_t12:,.0f}")
w("\nC4. Flagged, not changed (ruling 01b item 5)")
for it in FLAG:
    head(it)
    for r in pc[pc.item_no == it].itertuples():
        brk(r)
    for r in us[us.item_no == it].itertuples():
        w(f"   step {r.month:%Y-%m} price {r.P0:.2f}->{r.P1:.2f} dollars ratio {r.dollars_ratio:.2f}")
(s1 / "unit_breaks_handcheck.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"A {int((app.usd_t12 > 0).sum())} breaks on t12 items (+{int((pc.status == 'leave_alone').sum())} leave-alone); B {len(B)} of {len(pool)}; "
      f"hand read {int((pc.status == 'hand_read').sum())}; unexplained > $50K {len(big)} -> stage1/unit_breaks_handcheck.txt ({len(out)} lines)")
