"""Independent check of stage 1. Rebuilds the weekly demand table, SBC classes and ABC classes from the yearly
Parquet files with pandas/pyarrow only (no SQL), then compares them with the notebook's saved outputs.
Usage: python verify_stage1.py <base folder>   (default C:\\ds\\iowa-liquor)"""
import sys, re
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

base = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\ds\iowa-liquor")
CLASS_START, CLASS_END = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")
use = ["ordered_on", "item_no", "pack", "sales_bottles", "bottle_volume_ml", "state_bottle_cost", "state_bottle_retail", "sales_dollars", "source_part"]

frames = []
for f in sorted((base / "parquet").glob("sales_*.parquet")):
    t = pq.read_table(f, columns=use).to_pandas()
    frames.append(t)
df = pd.concat(frames, ignore_index=True)
del frames
print(f"rows read: {len(df):,}")

# duplicate parts: found independently by comparing whole parts within a year (row multisets)
full_cols = None
dup_parts = []
for f in sorted((base / "parquet").glob("sales_*.parquet")):
    t = pq.read_table(f).to_pandas()
    cols = [c for c in t.columns if c != "source_part"]
    key = pd.util.hash_pandas_object(t[cols], index=False)
    t = pd.DataFrame({"part": t["source_part"], "h": key})
    parts = sorted(t["part"].unique())
    seen = set()
    for p in parts:
        hs = set(t.loc[t["part"] == p, "h"])
        if seen and hs <= seen:
            dup_parts.append(p)
        seen |= hs
print("duplicate parts (pandas):", dup_parts)
df = df[~df["source_part"].isin(dup_parts)]
print(f"rows kept: {len(df):,}")

d = pd.to_datetime(df["ordered_on"], errors="coerce", format="ISO8601")
miss = d.isna()
if miss.any():
    d[miss] = pd.to_datetime(df.loc[miss, "ordered_on"], errors="coerce", format="%m/%d/%Y")
b = pd.to_numeric(df["sales_bottles"], errors="coerce")
c = pd.to_numeric(df["state_bottle_cost"].str.replace(r"[$,]", "", regex=True), errors="coerce")
r = pd.to_numeric(df["state_bottle_retail"].str.replace(r"[$,]", "", regex=True), errors="coerce")
sd = pd.to_numeric(df["sales_dollars"].str.replace(r"[$,]", "", regex=True), errors="coerce")
item = df["item_no"].str.strip()
vol = pd.to_numeric(df["bottle_volume_ml"], errors="coerce")
pk = pd.to_numeric(df["pack"], errors="coerce")
pk = pk.where(pk == np.floor(pk))
del df

# repair truncated prices (decision 32): a whole-number price takes the item's most common cents price that month whose
# whole-dollar part matches (ties: higher price); else the nearest-dated clean row of the item within 3 months either
# side with a matching whole-dollar part (ties: more rows that day, then higher price). No match: keep the state's total.
mon = d.dt.to_period("M")
def repair(price, nearest):
    k = pd.DataFrame({"item": item, "m": mon, "d": d, "p": price})
    cents = k[d.notna() & (k.p != np.floor(k.p))]
    mode = (cents.groupby(["item", "m", "p"]).size().rename("n").reset_index()
            .sort_values(["item", "m", "n", "p"], ascending=[True, True, False, False])
            .drop_duplicates(["item", "m"]).set_index(["item", "m"]).p)
    ref = pd.Series(mode.reindex(pd.MultiIndex.from_arrays([k.item, k.m])).values, index=k.index)
    whole = k.p.notna() & (k.p == np.floor(k.p)) & d.notna()
    fix = whole & (np.floor(ref) == k.p)
    out = k.p.copy(); out[fix] = ref[fix]
    fix2 = pd.Series(False, index=k.index)
    if nearest:
        need = k[whole & ~fix][["item", "d", "p"]].drop_duplicates()
        cl = cents.groupby(["item", "d", "p"]).size().rename("n").reset_index().rename(columns={"d": "cd", "p": "cp"})
        cl["w"] = np.floor(cl.cp)
        mm = need.merge(cl, left_on=["item", "p"], right_on=["item", "w"])
        mm = mm[(mm.cd >= mm.d - pd.DateOffset(months=3)) & (mm.cd <= mm.d + pd.DateOffset(months=3))].copy()
        mm["gap"] = (mm.cd - mm.d).abs()
        mm = (mm.sort_values(["item", "d", "p", "gap", "n", "cp"], ascending=[True, True, True, True, False, False])
                .drop_duplicates(["item", "d", "p"]))
        near = k[whole & ~fix].reset_index().merge(mm[["item", "d", "p", "cp"]], on=["item", "d", "p"]).set_index("index").cp
        out[near.index] = near
        fix2[near.index] = True
    return out, fix, fix2
c, fc, _ = repair(c, False)
r_raw = r.copy()
r, fr, fr2 = repair(r, True)
nc, nr = int(fc.sum()), int((fr | fr2).sum())
# decision 32 (judge addendum 2): keep the state's total; repair only a whole-number total less than $1 below
# bottles x a clean cents price
gap = b * r - sd
sig = (b > 0) & r.notna() & (r != np.floor(r)) & (sd == np.floor(sd)) & (gap > 0.005) & (gap < 1)
dollars = pd.Series(np.where(sig, b * r, sd), index=b.index)
print(f"repaired line totals (pandas): {int(sig.sum()):,}")
print(f"repaired lines (pandas): cost {nc:,}, retail {nr:,}")

# decisions 60-62 (judge's Addendum 8), written separately from the notebook. A unit break is a change of the month's
# most common recorded pack (most lines, then bottles, then smaller pack) by 1.8x or more, confirmed when
# (median line price after / before) / (old pack / new pack) is in 0.8-1.25 (0.67-1.5: hand read; else case size).
# Medians: old-pack lines in up to 3 order months before, new-pack lines in up to 3 order months from the break, each
# within 12 calendar months of it. Factor of a line = product of new/old pack over the applied breaks it precedes; inside
# a break's windows a line goes by its own price (nearer in log to P0 or P1), then pack, then month. Continuity per item:
# median monthly restated units after/before in 0.5-2 and dollars per restated unit in 0.67-1.5, else the item is cut at
# its last applied break (rows before it renamed item~preYYYYMM). Manual table: code/unit_breaks_manual.csv.
z_line = (b > 0) & (dollars == 0)
zb_line = (b.fillna(0) == 0) & (dollars.fillna(0) != 0)
zy = (pd.DataFrame({"year": d.dt.year, "zero_dollar_lines": z_line.astype(int), "zero_dollar_bottles": np.where(z_line, b, 0),
                    "zero_bottle_lines": zb_line.astype(int), "zero_bottle_dollars": np.where(zb_line, dollars, 0)})
        [d.notna()].groupby("year").sum())
zf = base / "stage1" / "evidence_zero_lines_by_year.csv"
if zf.exists():
    zn = pd.read_csv(zf).set_index("year")
    zj = zy.join(zn, rsuffix="_nb", how="outer").fillna(0)
    zok = all(np.allclose(zj[c], zj[c + "_nb"], atol=0.01) for c in zy.columns)
    print(f"{'OK ' if zok else 'BAD'} zero lines by year (decision 61): pandas {int(zy.zero_dollar_lines.sum()):,} zero-dollar, "
          f"{int(zy.zero_bottle_lines.sum()):,} zero-bottle | notebook {int(zn.zero_dollar_lines.sum()):,}, {int(zn.zero_bottle_lines.sum()):,}")

man_v = pd.read_csv(base / "stage1" / "unit_breaks.csv", dtype={"item_no": str, "month": str})   # frozen action table
man_v = {(r.item_no, r.month): r for r in man_v.itertuples()}
pos = (b > 0) & d.notna()
mstart = d.dt.to_period("M").dt.to_timestamp()
L = pd.DataFrame({"item": item[pos], "m": mstart[pos], "pk": pk[pos], "b": b[pos].astype(float), "usd": dollars[pos],
                  "z": z_line[pos]})
L["price"] = (L.usd / L.b).where(~L.z & L.usd.notna())
span = L[L.pk > 0].groupby("item").pk.agg(["min", "max"])
cand = span.index[span["max"] >= 1.8 * span["min"]]
Lc = L[L.item.isin(cand)]
recs = []          # one per pack change of 1.8x+
for it, g in Lc.groupby("item"):
    om = np.array(sorted(g.m.unique()))                         # order months of the item
    cnt = g[g.pk > 0].groupby(["m", "pk"]).b.agg(["size", "sum"]).reset_index()
    cnt = cnt.sort_values(["m", "size", "sum", "pk"], ascending=[True, False, False, True]).groupby("m").head(1)
    domm, domp = cnt.m.to_numpy(), cnt.pk.to_numpy()
    for k in range(1, len(domm)):
        A, B = domp[k - 1], domp[k]
        if A == B or max(A / B, B / A) < 1.8:
            continue
        brk_m = pd.Timestamp(domm[k]); j = int(np.searchsorted(om, domm[k]))
        key = (it, brk_m.strftime("%Y-%m")); mr = man_v.get(key)
        act_v = mr.action if mr is not None else None
        all_b, all_a = list(om[max(0, j - 3):j]), list(om[j:j + 3])
        before_m = [x for x in all_b if pd.Timestamp(x) >= brk_m - pd.DateOffset(months=12)]
        after_m = [x for x in all_a if pd.Timestamp(x) <= brk_m + pd.DateOffset(months=12)]
        p_old = g.price[g.m.isin(before_m) & (g.pk == A)].dropna()
        p_new = g.price[g.m.isin(after_m) & (g.pk == B)].dropna()
        if act_v in ("restate", "cut") and (len(p_old) == 0 or len(p_new) == 0):
            before_m, after_m = all_b, all_a                       # table entry with no capped window
            p_old = g.price[g.m.isin(before_m) & (g.pk == A)].dropna()
            p_new = g.price[g.m.isin(after_m) & (g.pk == B)].dropna()
        r = dict(item_no=it, month=brk_m, pack_old=A, pack_new=B, bm=before_m, am=after_m, P0=np.nan, P1=np.nan,
                 action=act_v, factor=float(mr.factor) if act_v in ("restate", "cut") else np.nan)
        if len(p_old) == 0 or len(p_new) == 0:
            r["status"] = "no_prices_in_cap"
        else:
            r["P0"], r["P1"] = p_old.median(), p_new.median()
            ratio = (r["P1"] / r["P0"]) * (B / A)
            r["status"] = ("confirmed" if 0.8 <= ratio <= 1.25 else "hand_read" if 0.67 <= ratio <= 1.5 else "case_size")
        recs.append(r)
ubv = pd.DataFrame(recs, columns=["item_no", "month", "pack_old", "pack_new", "bm", "am", "P0", "P1", "action", "factor", "status"])
applied = ubv[ubv.action.isin(["restate", "cut"])].sort_values(["item_no", "month"])
miss_v = ubv[(ubv.status == "confirmed") & ubv.action.isna()]
print(f"{'OK ' if len(miss_v) == 0 else 'BAD'} every break the rule confirms is in the frozen table (missing: {miss_v.item_no.tolist()})")

def before_mask(m_s, price_s, pk_s, x):
    """True where a line is on the old unit of applied break x"""
    early = (m_s < x.month).to_numpy()
    inwin = m_s.isin(list(x.bm) + list(x.am)).to_numpy()
    pkv = pk_s.to_numpy()
    by_pack = np.where(pkv == x.pack_old, True, np.where(pkv == x.pack_new, False, early))
    pv = price_s.to_numpy(float)
    with np.errstate(all="ignore"):
        lp0, lp1 = np.abs(np.log(pv / x.P0)), np.abs(np.log(pv / x.P1))
    own = np.where(np.isfinite(pv) & np.isfinite(lp0) & np.isfinite(lp1), lp0 < lp1, by_pack)
    return np.where(inwin, own, early)

cont_v, cut_v = {}, {}
for it, bk in applied.groupby("item_no"):
    g = Lc[Lc.item == it]
    f = np.ones(len(g))
    for x in bk.itertuples():
        f = f * np.where(before_mask(g.m, g.price, g.pk, x), x.factor, 1.0)
    rb = g.b.to_numpy() * f; good_all = True
    for x in bk.itertuples():
        side_b, side_a = g.m.isin(x.bm).to_numpy(), g.m.isin(x.am).to_numpy()
        units_b = pd.Series(rb[side_b], index=g.m.to_numpy()[side_b]).groupby(level=0).sum().median()
        units_a = pd.Series(rb[side_a], index=g.m.to_numpy()[side_a]).groupby(level=0).sum().median()
        priced = g.price.notna().to_numpy()
        pr_b = g.usd.to_numpy()[side_b & priced].sum() / rb[side_b & priced].sum() if (side_b & priced).any() else np.nan
        pr_a = g.usd.to_numpy()[side_a & priced].sum() / rb[side_a & priced].sum() if (side_a & priced).any() else np.nan
        okc = bool(0.5 <= units_a / units_b <= 2 and 0.67 <= pr_a / pr_b <= 1.5)
        cont_v[(it, x.month)] = okc; good_all &= okc
    if not good_all or (bk.action == "cut").any():
        cut_v[it] = bk.iloc[-1]
ubv["outcome"] = [("cut_at_last_break" if r.item_no in cut_v else "restated") if r.action in ("restate", "cut") else "not_applied"
                  for r in ubv.itertuples()]
print(f"unit breaks (pandas): {len(ubv)} pack changes of 1.8x+; applied {len(applied)} on {applied.item_no.nunique()} items; "
      f"cut by continuity {len(cut_v)}")
ubn_f = base / "stage1" / "unit_pack_changes_all.csv"
if ubn_f.exists():
    ubn = pd.read_csv(ubn_f, dtype={"item_no": str}, parse_dates=["month"])
    kv = set(zip(ubv.item_no, ubv.month.dt.strftime("%Y-%m"), ubv.status, ubv.action.fillna("-"), ubv.outcome))
    kn = set(zip(ubn.item_no, ubn.month.dt.strftime("%Y-%m"), ubn.status, ubn.action.fillna("-"), ubn.outcome))
    print(f"unit break list matches the notebook: {kv == kn} (pandas only {len(kv - kn)}, notebook only {len(kn - kv)})")

_pc_keys = set(zip(ubv.item_no, ubv.month.dt.strftime("%Y-%m")))
date_cuts_v = [k for k, r in man_v.items() if r.action == "cut" and k not in _pc_keys]
print(f"date cuts in the frozen table (pandas): {sorted(date_cuts_v)}")

def apply_ub(item_s, mon_s, price_s, pk_s, use_s):
    """bottle multiplier and item number per line, from the pandas break list (mon_s: month-start timestamps;
    use_s: lines with bottles > 0 and a date, the only lines the rule looks at)"""
    mult = pd.Series(1.0, index=item_s.index); name = item_s.copy()
    for it, bk in applied.groupby("item_no"):
        idx = item_s.index[(item_s == it) & use_s]
        if not len(idx):
            continue
        m_i, p_i, k_i = mon_s[idx], price_s[idx], pk_s[idx]
        if it in cut_v:
            x = cut_v[it]
            pre = before_mask(m_i, p_i, k_i, x)
            name[idx[pre]] = f"{it}~pre{x.month:%Y%m}"
        else:
            f = np.ones(len(idx))
            for x in bk.itertuples():
                f = f * np.where(before_mask(m_i, p_i, k_i, x), x.factor, 1.0)
            mult[idx] = f
    # date cuts (ruling 01d A3): table cut rows that match no pack change; earlier lines get a ~pre name, multiplier 1
    for (it, mo) in date_cuts_v:
        idx = item_s.index[(item_s == it) & use_s & (mon_s < pd.Timestamp(mo + "-01"))]
        mult[idx] = 1.0; name[idx] = f"{it}~pre{mo.replace('-', '')}"
    return mult, name
with np.errstate(all="ignore"):
    price_all = (dollars / b).where(~z_line & dollars.notna() & (b > 0))
    _mu, item = apply_ub(item, mstart, price_all, pk, pos)
b = b.astype(float) * _mu

dmin, dmax = d.min(), d.max()
first = dmin if dmin.weekday() == 0 else dmin - pd.Timedelta(days=dmin.weekday()) + pd.Timedelta(days=7)
last = dmax - pd.Timedelta(days=dmax.weekday())
if last + pd.Timedelta(days=6) > dmax:
    last -= pd.Timedelta(days=7)

ok = (b > 0) & d.notna()
x = pd.DataFrame({"item_no": item[ok].values, "date": d[ok].values, "b": b[ok].values, "spend": dollars[ok].values})
x["week"] = x["date"] - pd.to_timedelta(x["date"].dt.weekday, unit="D")
x = x[(x["week"] >= first) & (x["week"] <= last)]
iw = x.groupby(["item_no", "week"], sort=False).agg(bottles=("b", "sum"), spend=("spend", "sum")).reset_index()
del x

# zero fill: each item from its first demand week to the last complete week
start = iw.groupby("item_no")["week"].min()
nweeks = ((last - start).dt.days // 7 + 1).astype(int)
full = pd.DataFrame({"item_no": np.repeat(start.index.values, nweeks.values)})
full["week"] = np.repeat(start.values, nweeks.values) + pd.to_timedelta(
    np.concatenate([np.arange(n) for n in nweeks.values]) * 7, unit="D")
full = full.merge(iw, on=["item_no", "week"], how="left").fillna({"bottles": 0, "spend": 0})

# SBC on the class window
w = full[(full["week"] >= CLASS_START) & (full["week"] <= CLASS_END)]
nz = w[w["bottles"] > 0]
g = w.groupby("item_no")
s = pd.DataFrame({"n_weeks": g.size()})
s["n_demand_weeks"] = nz.groupby("item_no").size().reindex(s.index, fill_value=0)
s["mean"] = nz.groupby("item_no")["bottles"].mean()
s["sd"] = nz.groupby("item_no")["bottles"].std(ddof=1)
s["last_demand"] = nz.groupby("item_no")["week"].max()
s["adi"] = s["n_weeks"] / s["n_demand_weeks"].replace(0, np.nan)
s["cv2"] = (s["sd"] / s["mean"]) ** 2
cutoff = CLASS_END - pd.Timedelta(days=26 * 7)
cls = np.select(
    [s["n_demand_weeks"] == 0, s["last_demand"] < cutoff, s["n_demand_weeks"] < 2,
     (s["adi"] < 1.32) & (s["cv2"] < 0.49), s["adi"] < 1.32, s["cv2"] < 0.49],
    ["no demand in window", "inactive", "too few demands", "smooth", "erratic", "intermittent"], "lumpy")
s["sbc_class"] = cls

# ABC on window spend; the item that crosses a cut-off belongs to the higher class
sp = w.groupby("item_no")["spend"].sum()
sp = sp[sp > 0]
sp = sp.reset_index().sort_values(["spend", "item_no"], ascending=[False, True]).set_index("item_no")["spend"]
share = sp / sp.sum()
before = share.cumsum() - share
abc = pd.Series(np.where(before < 0.80, "A", np.where(before < 0.95, "B", "C")), index=sp.index)
s["abc_class"] = abc.reindex(s.index).fillna("-")

# compare
out = base / "stage1"
nbw = pq.read_table(out / "weekly_demand.parquet").to_pandas()
nbc = pd.read_csv(out / "item_classes.csv", dtype={"item_no": str}).set_index("item_no")
print("complete weeks:", first.date(), "to", last.date())
checks = {
    "item-week rows": (len(full), len(nbw)),
    "total bottles": (full["bottles"].sum(), nbw["bottles"].sum()),
    "zero weeks": (int((full["bottles"] == 0).sum()), int((nbw["bottles"] == 0).sum())),
    "classified items": (len(s), len(nbc)),
}
for k, (a, bb) in checks.items():
    print(f"{'OK ' if np.isclose(a, bb) else 'BAD'} {k}: pandas {a:,.0f} | notebook {bb:,.0f}")
j = s.join(nbc, rsuffix="_nb", how="outer")
print(f"max |ADI diff| {np.nanmax(np.abs(j['adi'] - j['adi_nb'])):.2e}   max |CV2 diff| {np.nanmax(np.abs(j['cv2'] - j['cv2_nb'])):.2e}")
print(f"SBC class mismatches: {(j['sbc_class'] != j['sbc_class_nb']).sum()}   ABC class mismatches: {(j['abc_class'] != j['abc_class_nb']).sum()}")
print("\nSBC counts (pandas):", s["sbc_class"].value_counts().to_dict())
print("ABC counts (pandas):", s["abc_class"].value_counts().sort_index().to_dict())
print("\nABC x SBC items (pandas):")
print(pd.crosstab(s["abc_class"], s["sbc_class"]))

# ---- monthly table and monthly SBC, rebuilt from the same cleaned lines ----
import datetime as dt
def hols(y):
    def nth(m, wd, n):
        if n > 0:
            d = dt.date(y, m, 1); d += dt.timedelta((wd - d.weekday()) % 7); return d + dt.timedelta(7 * (n - 1))
        d = (dt.date(y, m + 1, 1) if m < 12 else dt.date(y + 1, 1, 1)) - dt.timedelta(1)
        return d - dt.timedelta((d.weekday() - wd) % 7)
    obs = lambda d: d - dt.timedelta(1) if d.weekday() == 5 else d + dt.timedelta(1) if d.weekday() == 6 else d
    t = nth(11, 3, 4)
    return [obs(dt.date(y, 1, 1)), nth(1, 0, 3), nth(5, 0, -1), obs(dt.date(y, 7, 4)), nth(9, 0, 1),
            obs(dt.date(y, 11, 11)), t, t + dt.timedelta(1), obs(dt.date(y, 12, 25))]
H = [h for y in range(2011, 2028) for h in hols(y)]
last_data_m = dmax.to_period("M")
month_end = last_data_m.to_timestamp(how="end").normalize()
last_cal = np.busday_offset(np.datetime64(month_end.date(), "D"), 0, roll="backward", holidays=H)
complete = np.datetime64(dmax.date()) >= last_cal
origin = last_data_m if complete else last_data_m - 1
print(f"\nlast data month {last_data_m}, last calendar order day {last_cal}, complete {complete}, origin {origin}")

mo = pd.DataFrame({"item_no": item[ok].values, "m": d[ok].dt.to_period("M").values, "b": b[ok].values,
                   "dol": dollars[ok].values})
im = mo.groupby(["item_no", "m"]).agg(bottles=("b", "sum"), dol=("dol", "sum")).reset_index()
first_m = im.groupby("item_no").m.min()
nm = np.array([(last_data_m - fm).n + 1 for fm in first_m.values])
pm = pd.DataFrame({"item_no": np.repeat(first_m.index.values, nm),
                   "m": np.concatenate([pd.period_range(fm, last_data_m, freq="M") for fm in first_m.values])})
pm = pm.merge(im, on=["item_no", "m"], how="left").fillna({"bottles": 0, "dol": 0})
nbm = pq.read_table(base / "stage1" / "product_month.parquet").to_pandas()
print(f"{'OK ' if len(pm) == len(nbm) else 'BAD'} item-month rows: pandas {len(pm):,} | notebook {len(nbm):,}")
print(f"{'OK ' if np.isclose(pm.bottles.sum(), nbm.bottles.sum()) else 'BAD'} monthly bottles: pandas {pm.bottles.sum():,.0f} | notebook {nbm.bottles.sum():,.0f}")
print(f"{'OK ' if np.isclose(pm.dol.sum(), nbm.dollars_retail.sum()) else 'BAD'} repaired retail dollars: pandas {pm.dol.sum():,.2f} | notebook {nbm.dollars_retail.sum():,.2f}")
print(f"zero share: pandas {(pm.bottles == 0).mean():.4f} | notebook {(nbm.bottles == 0).mean():.4f}")

# monthly classes at the origin: active = order in the 12 months to the origin; window = 24 months to the origin
act = set(pm[(pm.m > origin - 12) & (pm.m <= origin) & (pm.bottles > 0)].item_no)
w = pm[(pm.m > origin - 24) & (pm.m <= origin) & pm.item_no.isin(act)]
nzm = w[w.bottles > 0]
sm = pd.DataFrame({"n": w.groupby("item_no").size()})
sm["k"] = nzm.groupby("item_no").size().reindex(sm.index, fill_value=0)
sm["cv2"] = (nzm.groupby("item_no").bottles.std(ddof=1) / nzm.groupby("item_no").bottles.mean()) ** 2
sm["adi"] = sm.n / sm.k
sm["cls"] = np.select([sm.k < 6, (sm.adi < 1.32) & (sm.cv2 < 0.49), sm.adi < 1.32, sm.cv2 < 0.49],
                      ["too short", "smooth", "erratic", "intermittent"], "lumpy")
nbcls = pd.read_csv(base / "stage1" / "monthly_classes_last_origin.csv", dtype={"item_no": str}).set_index("item_no")
jj = sm.join(nbcls, how="outer", rsuffix="_nb")
print(f"monthly classes: pandas {len(sm):,} items | notebook {len(nbcls):,}; class mismatches {(jj.cls != jj.sbc_class).sum()}")
print("monthly SBC counts (pandas):", sm.cls.value_counts().to_dict())

# ---- linked series (decision 42), rebuilt independently ----
cols = ["ordered_on", "item_no", "im_desc", "pack", "bottle_volume_ml", "category_name", "sales_bottles", "sales_dollars", "source_part"]
parts = []
for f in sorted((base / "parquet").glob("sales_*.parquet")):
    t = pq.read_table(f, columns=cols).to_pandas()
    t = t[~t.source_part.isin(dup_parts)]
    dd = pd.to_datetime(t.ordered_on, errors="coerce", format="ISO8601")
    t = t[(pd.to_numeric(t.sales_bottles, errors="coerce") > 0) & dd.notna()].assign(day=dd)
    t["item_no"] = t.item_no.str.strip()
    if len(applied):
        with np.errstate(all="ignore"):
            sd_t = pd.to_numeric(t.sales_dollars.str.replace(r"[$,]", "", regex=True), errors="coerce")
            pk_t = pd.to_numeric(t.pack, errors="coerce")
            t["item_no"] = apply_ub(t.item_no, t.day.dt.to_period("M").dt.to_timestamp(),
                                    (sd_t / pd.to_numeric(t.sales_bottles, errors="coerce")).where(sd_t != 0),
                                    pk_t.where(pk_t == np.floor(pk_t)), pd.Series(True, index=t.index))[1]
    t["d"] = t.im_desc.fillna("").map(lambda s: re.sub(r"\s+", " ", s).strip().upper())
    t["ml"] = pd.to_numeric(t.bottle_volume_ml, errors="coerce")
    parts.append(t.groupby(["item_no", "d", "ml", "category_name"], dropna=False)
                  .agg(n=("day", "size"), latest=("day", "max"), first=("day", "min")).reset_index())
    del t
at = pd.concat(parts).groupby(["item_no", "d", "ml", "category_name"], dropna=False).agg(
    n=("n", "sum"), latest=("latest", "max"), first=("first", "min")).reset_index()
span = at.groupby("item_no").agg(first_order=("first", "min"), last_order=("latest", "max"))
attr = (at.sort_values(["item_no", "n", "latest", "d", "ml", "category_name"],
                       ascending=[True, False, False, True, True, True], na_position="last")
          .drop_duplicates("item_no").set_index("item_no")[["d", "ml", "category_name"]].join(span))
# price per bottle near the handover (proposed guard): older's last 12 months, newer's first 12 months
lp = pd.DataFrame({"item_no": item[ok].values, "m": d[ok].dt.to_period("M").values, "p": (dollars[ok] / b[ok]).where(~z_line[ok]).values})
mm = lp[["item_no", "m"]].drop_duplicates().sort_values(["item_no", "m"])
mm["rf"] = mm.groupby("item_no").cumcount() + 1
mm["rl"] = mm.groupby("item_no").m.transform("size") - mm.rf + 1
lp = lp.merge(mm, on=["item_no", "m"])
attr = attr.join(lp[lp.rl <= 12].groupby("item_no").p.median().rename("p_last12"))
attr = attr.join(lp[lp.rf <= 12].groupby("item_no").p.median().rename("p_first12"))
del lp
PRICE_BAND = (0.67, 1.5)
# Addendum 3 rule: older a starts before newer b, a's last order within 90 days either side of b's first;
# link only one-to-one candidate pairs
cand = []
for key, g in attr.reset_index().groupby(["d", "ml"]):
    if len(g) < 2:
        continue
    for _, nb_ in g.iterrows():
        ok_ = g[(g.item_no != nb_.item_no) & (g.first_order < nb_.first_order)
                & (g.last_order >= nb_.first_order - pd.Timedelta(days=90))
                & (g.last_order <= nb_.first_order + pd.Timedelta(days=90))]
        if PRICE_BAND is not None:
            rat = ok_.p_last12 / nb_.p_first12 if nb_.p_first12 > 0 else ok_.p_last12 * np.nan
            ok_ = ok_[(rat >= PRICE_BAND[0]) & (rat <= PRICE_BAND[1])]
        cand += [(nb_.item_no, o) for o in ok_.item_no]
cdf = pd.DataFrame(cand, columns=["newer", "older"])
one = (cdf.groupby("newer").older.transform("size") == 1) & (cdf.groupby("older").newer.transform("size") == 1)
pred = dict(zip(cdf.newer[one], cdf.older[one]))
def _root(i):
    while i in pred:
        i = pred[i]
    return i
sid = pd.Series({i: _root(i) for i in attr.index}, name="series_id")
nbs = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str, "predecessor": str}).set_index("item_no")
js = nbs.join(sid, rsuffix="_pd", how="outer")
print(f"{'OK ' if (js.series_id == js.series_id_pd).all() else 'BAD'} series ids: pandas {sid.nunique():,} series, "
      f"{len(pred):,} links, {int((~one).sum()):,} ambiguous pairs | notebook {nbs.series_id.nunique():,} series; mismatched items {(js.series_id != js.series_id_pd).sum()}")

# series-month totals and classes at the origin (protocol 1.3: new under 12 months since first order; under 2 non-zero
# months = intermittent; ADI above 1.32 = intermittent or lumpy)
pm["series_id"] = pm.item_no.map(sid)
ps = pm.groupby(["series_id", "m"]).agg(bottles=("bottles", "sum"), dol=("dol", "sum")).reset_index()
nsm = pq.read_table(base / "stage1" / "series_month.parquet").to_pandas()
print(f"{'OK ' if len(ps) == len(nsm) else 'BAD'} series-month rows: pandas {len(ps):,} | notebook {len(nsm):,}")
print(f"{'OK ' if np.isclose(ps.bottles.sum(), nsm.bottles.sum()) and np.isclose(ps.dol.sum(), nsm.dollars_retail.sum()) else 'BAD'} "
      f"series-month bottles and dollars")
first_s = ps[ps.bottles > 0].groupby("series_id").m.min()
act = set(ps[(ps.m > origin - 12) & (ps.m <= origin) & (ps.bottles > 0)].series_id)
w = ps[(ps.m > origin - 24) & (ps.m <= origin) & ps.series_id.isin(act)]
nzs = w[w.bottles > 0]
ss = pd.DataFrame({"n": w.groupby("series_id").size()})
ss["k"] = nzs.groupby("series_id").size().reindex(ss.index, fill_value=0)
ss["cv2"] = ((nzs.groupby("series_id").bottles.std(ddof=1) / nzs.groupby("series_id").bottles.mean()) ** 2).reindex(ss.index).fillna(0)
ss["adi"] = ss.n / ss.k
ss["age"] = [(origin - first_s[i]).n + 1 for i in ss.index]
ss["cls"] = np.select([ss.age < 12, ss.k < 2, (ss.adi <= 1.32) & (ss.cv2 < 0.49), ss.adi <= 1.32, ss.cv2 < 0.49],
                      ["new", "intermittent", "smooth", "erratic", "intermittent"], "lumpy")
nbsc = pd.read_csv(base / "stage1" / "series_classes_last_origin.csv", dtype={"series_id": str}).set_index("series_id")
jc = ss.join(nbsc, how="outer", rsuffix="_nb")
print(f"series classes: pandas {len(ss):,} | notebook {len(nbsc):,}; class mismatches {(jc.cls != jc.demand_class).sum()}")
print("series class counts (pandas):", ss.cls.value_counts().to_dict())


# decision 51 liters for unit-break items, independent check: trailing-12 liters from the parquet files in the STATE'S
# recorded units. The single bottle is the unit with the larger pack at the item's last applied break, so a line holds
# max(pack before, pack after) / its own pack single bottles of its recorded size, times the size-history factor of
# that size (stage2/units_table.csv). Compared with stage2/units_series_t12.csv, which units_tiers.py builds from
# restated units x ml x factor.
uf, ut = base / "stage2" / "units_series_t12.csv", base / "stage2" / "units_table.csv"
if uf.exists() and ut.exists():
    fz = pd.read_csv(base / "stage1" / "unit_breaks.csv", dtype={"item_no": str})
    fz = fz[fz.action.isin(["restate", "cut"])]
    parts = []
    for f in sorted((base / "parquet").glob("sales_*.parquet")):
        t = pq.read_table(f, columns=["ordered_on", "item_no", "pack", "sales_bottles", "bottle_volume_ml", "source_part"]).to_pandas()
        parts.append(t[t.item_no.astype(str).str.strip().isin(set(fz.item_no))])
    u = pd.concat(parts, ignore_index=True); del parts
    u = u[~u.source_part.isin(dup_parts)]
    u["day"] = pd.to_datetime(u.ordered_on, errors="coerce", format="ISO8601")
    u = u[u.day > d.max() - pd.DateOffset(months=12)]
    u["item_no"] = u.item_no.astype(str).str.strip()
    u["b"] = pd.to_numeric(u.sales_bottles, errors="coerce"); u["ml"] = pd.to_numeric(u.bottle_volume_ml, errors="coerce")
    u["pk"] = pd.to_numeric(u.pack, errors="coerce")
    u = u[u.b > 0]
    last = fz.sort_values("month").groupby("item_no").tail(1).set_index("item_no")
    big = np.maximum(last.pack_before, last.pack_after)
    tb = pd.read_csv(ut, dtype={"item_no": str, "series_id": str})
    tb["pack_of"] = tb.item_no.map(np.maximum(1.0, last.pack_before / last.pack_after))
    tb["size_factor"] = np.where(tb.source.str.contains("unit break", na=False), tb.factor / tb.pack_of, tb.factor)
    szf = tb.set_index(["item_no", "ml"]).size_factor
    size = szf.reindex(list(zip(u.item_no, u.ml))).fillna(1.0).to_numpy()
    # a line carrying the old pack is in the old unit; any other pack (the new one, or a later ordinary case-size
    # change) is in the current unit
    pb_, pa_ = last.pack_before.reindex(u.item_no).to_numpy(), last.pack_after.reindex(u.item_no).to_numpy()
    singles = big.reindex(u.item_no).to_numpy() / np.where(u.pk.to_numpy() == pb_, pb_, pa_)
    u["liters"] = u.b * u.ml / 1e3 * singles * size
    nb = pd.read_csv(uf, dtype={"series_id": str}).set_index("series_id")
    isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
    # a cut item's old-unit lines before its break belong to its ~pre series
    cutl = last[last.action == "cut"] if "action" in last else last.iloc[0:0]
    sid_l = u.item_no.copy()
    for it, x in cutl.iterrows():
        bm_ = pd.Timestamp(x.month + "-01")
        pre_ = (u.item_no == it) & (u.pk == x.pack_before) & (u.day < bm_)
        sid_l[pre_] = f"{it}~pre{bm_:%Y%m}"
    g = u.assign(series_id=sid_l.map(isr).fillna(sid_l)).groupby("series_id").liters.sum()
    lcol = "liters_computed_t12" if "liters_computed_t12" in nb.columns else "liters_t12"   # held series keep the computed figure
    jj = pd.concat([g.rename("pandas"), nb[lcol].reindex(g.index).rename("units_tiers")], axis=1).dropna(subset=["units_tiers"])
    okl = np.allclose(jj.pandas, jj.units_tiers, rtol=1e-6)
    print(f"{'OK ' if okl else 'BAD'} decision 51 liters, unit-break series: pandas {jj.pandas.sum():,.1f} L | units_tiers "
          f"{jj.units_tiers.sum():,.1f} L; series {len(jj)}")
else:
    print("decision 51 liters check skipped: run stage2/units_tiers.py first")
