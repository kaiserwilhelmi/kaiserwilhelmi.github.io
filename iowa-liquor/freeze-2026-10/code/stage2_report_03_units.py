"""Units sections of 03-tuning.md (ruling 01e and its amendment). Read-only. Writes stage2/report_03_units.md.
Usage: python report_03_units.py <base>"""
import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
base = Path(sys.argv[1]); out = base / "stage2"
con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
s = pd.read_csv(out / "units_series_t12.csv", dtype={"series_id": str})
ck = pd.read_csv(out / "units_decision66_checks.csv", dtype={"series_id": str, "sibling": str})
ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str})
isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
L = []; w = L.append
tot = s.usd_t12.sum()
w("## Liters tiers after decision 66 (ruling 01e and amendment)")
w(""); w("| series | t12 $ | tier | size history | unit break | liters per unit (rule) | sibling price check | relabel bottles / price |")
w("|---|---:|---|---|---|---:|---|---|")
rs = ap[ap.outcome == "restated"].item_no.map(lambda i: isr.get(i, i)).unique()
for sid in sorted(rs, key=lambda x: -s.set_index("series_id").usd_t12.get(x, 0)):
    r = s[s.series_id == sid]
    if not len(r):
        w(f"| {sid} | 0 | (no t12 sales) | | | | | |"); continue
    r = r.iloc[0]; c = ck[ck.series_id == sid]
    pc = (f"{c.price_per_l_vs_sibling.iat[0]:.3f} vs {c.sibling.iat[0]} ({c.sibling_month.iat[0]})" if len(c) and pd.notna(c.sibling.iat[0]) else "-")
    rl = (f"{c.relabel_bottles_ratio.iat[0]:.4f} / {c.relabel_price_ratio.iat[0]:.3f} ({c.relabel_month.iat[0]})" if len(c) and pd.notna(c.relabel_month.iat[0]) else "-")
    w(f"| {sid} | {r.usd_t12:,.0f} | {r.tier} | {'yes' if r.has_size else 'no'} | {'yes' if r.has_break else 'no'} | {r.lpu:.3f} L | {pc} | {rl} |")
w(""); w("- **84207 is a borderline case**: bottles per month move 10.04% across its Aug 2019 relabel (price flat at $9.00), just over the "
         "judge's fixed 10% line, so it goes to unknown. 84143 (99 Cinnamon) moves 9.97% and stays proven. Not changed by hand.")
w(f"- 2a. Standard-tier series at 200 ml or less: {int(((s.tier == 'standard') & (s.ml <= 200)).sum())} "
  f"(${s.usd_t12[(s.tier == 'standard') & (s.ml <= 200)].sum():,.0f}, {100 * s.usd_t12[(s.tier == 'standard') & (s.ml <= 200)].sum() / tot:.2f}% of t12 dollars). "
  "They are small bottles with no size history and no dollars-per-liter flag; the largest are listed below.")
w(f"- 2b. Proven series with size history and no unit break (they stay proven): {int(((s.tier == 'proven') & s.has_size & ~s.has_break).sum())} "
  f"(${s.usd_t12[(s.tier == 'proven') & s.has_size & ~s.has_break].sum():,.0f}, {100 * s.usd_t12[(s.tier == 'proven') & s.has_size & ~s.has_break].sum() / tot:.2f}%).")
fl = s.category_screen_flag.astype(str) == "True"
w(f"- 13. Category dollars-per-liter screen (below 1/4 or above 4x the category's dollar-weighted median): {int(fl.sum())} series flagged "
  f"(${s.usd_t12[fl].sum():,.0f}); moved to unknown (200 ml or less, or a pack mark): {int((fl & (s.tier == 'unknown')).sum())} "
  f"(${s.usd_t12[fl & (s.tier == 'unknown')].sum():,.0f}); listed for a hand read, not moved: {int((fl & (s.tier == 'standard')).sum())} "
  f"(${s.usd_t12[fl & (s.tier == 'standard')].sum():,.0f}; `stage2\\units_tiers_hand_read.csv`).")
u = s[s.tier == "unknown"]
w(f"- 14. Liters cover {100 * (1 - u.usd_t12.sum() / tot):.2f}% of trailing-12 dollars; series left out of liters: {len(u)}.")
w(""); w("Largest standard-tier series at 200 ml or less:"); w("")
w("| series | description | ml | t12 $ | $ per L | ratio to category |"); w("|---|---|---:|---:|---:|---:|")
for r in s[(s.tier == "standard") & (s.ml <= 200)].nlargest(10, "usd_t12").itertuples():
    w(f"| {r.series_id} | {str(r.d)[:40]} | {r.ml:g} | {r.usd_t12:,.0f} | {r.usd_per_l:,.1f} | {r.ratio_category:.2f} |")
# item 7: relabel tables for the restated series with size history
w(""); w("## Relabel 600 ml -> 50 ml, 3 months each side (amendment item 7, 10% rule)"); w("")
for r in ck.itertuples():
    its = [i for i, sid in isr.items() if sid == r.series_id]
    if pd.isna(r.relabel_month):
        continue
    mo = pd.Timestamp(r.relabel_month + "-01")
    q = con.execute("""SELECT strftime(date_trunc('month', order_date), '%Y-%m') AS m, MODE(bottle_volume_ml) AS ml, SUM(sales_bottles_recorded) AS b,
        SUM(sales_dollars) / SUM(sales_bottles_recorded) AS p FROM sales WHERE item_no IN (SELECT UNNEST(?::VARCHAR[])) AND sales_bottles_recorded > 0
        AND order_date >= ? AND order_date < ? GROUP BY 1 ORDER BY 1""", [its, (mo - pd.DateOffset(months=3)).date(), (mo + pd.DateOffset(months=3)).date()]).df()
    w(f"- **{r.series_id}** ({r.relabel_month}): " + "; ".join(f"{x.m} {x.ml:g} ml {x.b:,.0f} btl ${x.p:.2f}" for x in q.itertuples())
      + f" -> bottles x{r.relabel_bottles_ratio:.4f}, price x{r.relabel_price_ratio:.3f}: {'level within 10%' if r.relabel_ok else 'moves over 10% (unknown)'}"
      + f"; tier **{s.set_index('series_id').tier.get(r.series_id, '-')}**")
# item 8: when 84172 and 101180 went 10 -> 12 or $7.74 -> $6.45
w(""); w("## 84172 and 101180: the month the pack went 10 -> 12 or the price $7.74 -> $6.45 (amendment item 8, report only)"); w("")
for it in ("84172", "101180"):
    q = con.execute("""SELECT CAST(date_trunc('month', order_date) AS DATE) AS m, string_agg(DISTINCT CAST(pack AS VARCHAR), '/') AS packs,
        SUM(sales_bottles_recorded) AS b, SUM(sales_dollars) AS usd, SUM(sales_dollars) / SUM(sales_bottles_recorded) AS p
        FROM sales WHERE regexp_replace(item_no, '~pre.*', '') = ? AND sales_bottles_recorded > 0 AND order_date < DATE '2023-05-01'
        GROUP BY 1 ORDER BY 1""", [it]).df()
    q["m"] = pd.to_datetime(q.m)
    # the change the ruling asks for: recorded pack 10 -> 12, or price from about $7.74 to about $6.45
    pk_to12 = q.packs.str.contains("12") & ~q.packs.shift().fillna("").str.contains("12")
    pr_to645 = ((q.p - 6.45).abs() < 0.10) & ((q.p.shift() - 7.74).abs() < 0.30)
    ch = [i for i in q.index[pk_to12 | pr_to645] if i > 0]
    if not ch:
        w(f"- {it}: no pack or price change before May 2023 (pack {q.packs.iat[0]}, ${q.p.median():.2f} throughout)"); continue
    for i in ch[:3]:
        win = q.iloc[max(0, i - 3):i + 3]
        w(f"- {it}, change at {q.m[i]:%Y-%m}: " + "; ".join(f"{x.m:%Y-%m} pack {x.packs} {x.b:,.0f} btl ${x.usd:,.0f} ${x.p:.2f}" for x in win.itertuples()))
(out / "report_03_units.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"report_03_units.md: {len(L)} lines")
