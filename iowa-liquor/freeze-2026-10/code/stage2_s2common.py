"""Stage 2 shared pieces (evaluation protocol 1.4): data matrices, effective order days as of an origin, demand classes,
the selection metric, and the scoring filters. Everything a model sees at origin o uses months up to o only.
Months are integer column indexes into MONTHS (Jan 2012 = 0)."""
import os, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd, duckdb

Q = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
H = (1, 2, 3)
FUTURE = 6      # months past the data end with effective order days (for the live forecast)
SEPARATE = ["87035", "28081"]   # scored separately (ruling 01d B6): Skrewball mini (price toggles), Prairie Fire mini


def progress(base, msg, done=None, total=None, t_start=None):
    """One timestamped line in <base>/logs/progress.log for Dawson to watch (PowerShell: Get-Content -Wait)."""
    import time
    line = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    if done is not None and total:
        line += f"  [{done}/{total}]"
        if t_start is not None and done:
            el = time.time() - t_start; eta = el / done * (total - done)
            line += f"  elapsed {el / 60:.0f} min, ETA {eta / 60:.0f} min ({(dt.datetime.now() + dt.timedelta(seconds=eta)):%H:%M})"
    p = Path(base) / "logs"; p.mkdir(parents=True, exist_ok=True)
    with open(p / "progress.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _nth(y, m, wd, n):
    if n > 0:
        d = dt.date(y, m, 1); d += dt.timedelta((wd - d.weekday()) % 7); return d + dt.timedelta(7 * (n - 1))
    d = dt.date(y, m + 1, 1) - dt.timedelta(1) if m < 12 else dt.date(y, 12, 31)
    return d - dt.timedelta((d.weekday() - wd) % 7)


def _obs(d):
    return d - dt.timedelta(1) if d.weekday() == 5 else d + dt.timedelta(1) if d.weekday() == 6 else d


def iowa_holidays_named(y):     # same rule as the stage 1 notebook (section 9c)
    th = _nth(y, 11, 3, 4)
    return {_obs(dt.date(y, 1, 1)): "New Year's Day", _nth(y, 1, 0, 3): "Martin Luther King Jr. Day",
            _nth(y, 5, 0, -1): "Memorial Day", _obs(dt.date(y, 7, 4)): "Independence Day", _nth(y, 9, 0, 1): "Labor Day",
            _obs(dt.date(y, 11, 11)): "Veterans Day", th: "Thanksgiving", th + dt.timedelta(1): "Day after Thanksgiving",
            _obs(dt.date(y, 12, 25)): "Christmas"}


class Data:
    def __init__(self, base, asof=None):
        """asof: 'YYYY-MM' to drop every month after it (the stage 2 truncation test). Static attributes (the series
        map, links and category) are kept as they are; everything that varies by month is cut."""
        base = Path(base)
        self.base = base
        self.asof = asof
        cut = f"DATE '{(pd.Period(asof, freq='M') + 1).start_time.date()}'" if asof else "DATE '9999-01-01'"
        con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
        sm = con.execute(f"SELECT series_id, month_start, bottles, dollars_retail FROM series_month WHERE month_start < {cut}").df()
        links = con.execute('''SELECT s.series_id, s.first_order AS newer_first, p.last_order AS older_last
                               FROM item_series s JOIN item_series p ON p.item_no = s.predecessor''').df()
        wd_days = con.execute(f"SELECT month_start, dow, days FROM month_weekday_days WHERE month_start < {cut}").df()
        wd_bot = con.execute(f"SELECT month_start, dow, bottles FROM month_weekday_bottles WHERE month_start < {cut}").df()
        # series attributes for the tree model: category of the series id's own item number; vendor by month (latest
        # vendor among the series' item numbers ordered that month)
        # category: the series' most common non-blank category by bottles (blank-category lines take it; ruling 01b item 7)
        # ties broken explicitly (more bottles, then more lines, then name): arg_max picked arbitrarily between equal
        # counts, which changed the tree model's inputs from one load to the next (found by the truncation test)
        attr = con.execute('''WITH c AS (SELECT i.series_id, s.category_name AS category, SUM(s.sales_bottles) AS b, COUNT(*) AS n
                                         FROM sales s JOIN item_series i USING (item_no)
                                         WHERE s.sales_bottles > 0 AND trim(COALESCE(s.category_name, '')) <> '' GROUP BY 1, 2),
                              r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY b DESC, n DESC, category) AS k FROM c)
                              SELECT series_id, category FROM r WHERE k = 1''').df()
        # recorded / restated units per series-month (decision 50: count-based quantiles in the recorded unit)
        rec = con.execute(f'''SELECT i.series_id, date_trunc('month', s.order_date) AS month_start,
                                    SUM(s.sales_bottles_recorded) / SUM(s.sales_bottles) AS k
                             FROM sales s JOIN item_series i USING (item_no) WHERE s.sales_bottles > 0 AND s.order_date < {cut} GROUP BY 1, 2''').df()
        vend = con.execute(f'''SELECT s.series_id, v.month_start, MAX(v.vendor_name) AS vendor
                              FROM item_vendor_month v JOIN item_series s USING (item_no) WHERE v.month_start < {cut} GROUP BY 1, 2''').df()
        con.close()
        self.months = pd.period_range("2012-01", sm.month_start.max().strftime("%Y-%m"), freq="M")
        self.mi = {p: i for i, p in enumerate(self.months)}
        self.sids = np.sort(sm.series_id.unique())
        si = {s: i for i, s in enumerate(self.sids)}
        S, M = len(self.sids), len(self.months)
        self.S, self.M = S, M
        Y = np.full((S, M), np.nan); D = np.zeros((S, M))
        r = sm.series_id.map(si).to_numpy(); c = pd.PeriodIndex(sm.month_start, freq="M").map(self.mi).to_numpy()
        Y[r, c] = sm.bottles.to_numpy(float); D[r, c] = sm.dollars_retail.fillna(0).to_numpy(float)
        self.Y, self.D = Y, D
        rec = rec[rec.series_id.isin(si) & (pd.PeriodIndex(rec.month_start, freq="M") <= self.months[-1])]
        K = np.full((S, M), np.nan)
        K[rec.series_id.map(si).to_numpy(), pd.PeriodIndex(rec.month_start, freq="M").map(self.mi).to_numpy()] = rec.k.to_numpy(float)
        self.K_rec = pd.DataFrame(K).T.ffill().T.fillna(1.0).to_numpy()   # recorded units per restated unit, as of each month
        self.first = np.argmax(~np.isnan(Y), axis=1)
        wd_days["m"] = pd.PeriodIndex(wd_days.month_start, freq="M").map(self.mi)
        wd_bot["m"] = pd.PeriodIndex(wd_bot.month_start, freq="M").map(self.mi)
        self.DAYS = np.zeros((M + FUTURE, 8))
        self.DAYS[wd_days.m.to_numpy(), wd_days.dow.to_numpy()] = wd_days.days.to_numpy()
        # future months: weekend days count; weekdays less the holidays kept by the stage 1 rule (a holiday that
        # carried orders in at least half of years is dropped from the list)
        hb = pd.read_csv(base / "stage1" / "holiday_bottles_by_year.csv")
        g = hb.groupby("holiday").agg(n=("year", "size"), c=("carries_orders", "sum"))
        dropped = set(g.index[g.c >= 0.5 * g.n])
        self.holidays_dropped = sorted(dropped)
        for k in range(FUTURE):
            p = self.months[-1] + k + 1
            hol = {d for d, n in iowa_holidays_named(p.year).items() if n not in dropped}
            for day in pd.date_range(p.start_time, p.end_time, freq="D").date:
                dow = day.isoweekday()
                if dow >= 6 or day not in hol:
                    self.DAYS[M + k, dow] += 1
        self.BOT = np.zeros((M, 8)); self.BOT[wd_bot.m.to_numpy(), wd_bot.dow.to_numpy()] = wd_bot.bottles.to_numpy(float)
        links["nf"] = pd.PeriodIndex(links.newer_first, freq="M").map(self.mi)
        links["ol"] = pd.to_datetime(links.older_last)
        links["sid"] = links.series_id.map(si)
        self.links = links
        self.category = pd.Series(self.sids).map(attr.set_index("series_id").category).fillna("UNKNOWN").to_numpy()
        # scored separately (ruling 01d B6): out of the selection metric and the headline score, own scores beside it
        self.separate = np.isin(self.sids, SEPARATE)
        # unit_change_window (ruling 01d B8, amendment item 1): the break month and the month after of every restated
        # break; scores are shown with these item-months in (the selection metric) and out
        self.window = np.zeros((S, M), bool)
        apf = base / "stage1" / "unit_breaks_applied.csv"
        if apf.exists():
            ap = pd.read_csv(apf, dtype={"item_no": str}, parse_dates=["month"])
            ap = ap[ap.outcome == "restated"]
            isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
            for r in ap.itertuples():
                sid = si.get(isr.get(r.item_no, r.item_no)); m0 = self.mi.get(pd.Period(r.month, freq="M"))
                if sid is not None and m0 is not None:
                    self.window[sid, m0:min(m0 + 2, M)] = True
        vend["sid"] = vend.series_id.map(si); vend["m"] = pd.PeriodIndex(vend.month_start, freq="M").map(self.mi)
        V = np.full((S, M), None, dtype=object); V[vend.sid.to_numpy(), vend.m.to_numpy()] = vend.vendor.to_numpy()
        self.vendor_by_month = pd.DataFrame(V).T.ffill().T.to_numpy()   # vendor as of each month (last seen)
        self.cols = np.arange(M)

    # effective order days of every month, with weekday shares of the 24 months up to origin o (protocol section 1;
    # an origin in the first 24 months uses the earliest 24 months)
    def eff_days(self, o):
        lo = max(o - 23, 0); hi = lo + 23 if o - 23 < 0 else o
        sh = self.BOT[lo:hi + 1].sum(0); sh = sh / sh.sum()
        return 5 * (self.DAYS * sh).sum(1)

    def hist(self, X, o):
        return np.where(self.cols[None, :] <= o, X, np.nan)

    def active(self, o):
        win = (self.cols[None, :] > o - 12) & (self.cols[None, :] <= o)
        return (self.first <= o) & (np.nansum(np.where(win, self.Y, 0), axis=1) > 0)

    def scale(self, o):
        # section 4: mean absolute month-to-month change of monthly bottles from the first order month to the origin
        with np.errstate(all="ignore"):
            return np.nanmean(np.abs(np.diff(self.hist(self.Y, o), axis=1)), axis=1)

    def open_handover(self, o):
        end = self.months[o].to_timestamp(how="end")
        l = self.links[(self.links.nf <= o) & (self.links.ol > end)]
        out = np.zeros(self.S, bool); out[l.sid.to_numpy()] = True
        return out

    def weight12(self, o):
        return self.D[:, max(o - 11, 0):o + 1].sum(1)

    def classes(self, o):
        """protocol 1.3/1.4 section 6, monthly bottles over the 24 months to the origin:
        'new' (under 12 months since first order), 'intermittent' (ADI > 1.32, or under 2 non-zero months; lumpy is
        pooled here), 'regular' (smooth or erratic). Returns (pool class, SBC label) arrays; '' for inactive."""
        age = o - self.first + 1
        w = np.where((self.cols[None, :] > o - 24) & (self.cols[None, :] <= o), self.Y, np.nan)
        n = np.sum(~np.isnan(w), axis=1)
        nzm = np.where(w > 0, w, np.nan)
        nz = np.sum(~np.isnan(nzm), axis=1)
        with np.errstate(all="ignore"):
            adi = n / nz
            mu = np.nanmean(nzm, axis=1); sd = np.nanstd(nzm, axis=1, ddof=1)
            cv2 = np.where(nz >= 2, (sd / mu) ** 2, 0.0)
        sbc = np.select([age < 12, nz < 2, (adi <= 1.32) & (cv2 < 0.49), adi <= 1.32, cv2 < 0.49],
                        ["new", "intermittent", "smooth", "erratic", "intermittent"], "lumpy")
        pool = np.select([sbc == "new", np.isin(sbc, ["intermittent", "lumpy"])], ["new", "intermittent"], "regular")
        act = self.active(o)
        return np.where(act, pool, ""), np.where(act, sbc, "")


def pinball(y, qf):
    d = y[:, None] - qf
    return np.where(d >= 0, d * Q, -d * (1 - Q)).mean(1)


def scored_mask(data, o, t):
    sc = data.scale(o)
    ok = data.active(o) & np.isfinite(sc) & (sc > 0) & ~np.isnan(data.Y[:, t]) & ~data.separate
    return ok, ok & ~data.open_handover(o), sc


def metric(data, fc, by=("layer", "h")):
    """fc: DataFrame with sid, o, h, layer, q05..q95 (monthly bottles). Adds the selection metric per origin, then
    averages over origins. Open handover windows are excluded; also returned with them for the 2026 report."""
    rows = []
    qc = [f"q{int(round(q * 100)):02d}" for q in Q]
    for (o, h), g in fc.groupby(["o", "h"]):
        t = o + h
        if t >= data.M:
            continue
        ok_all, ok, sc = scored_mask(data, o, t)
        w12 = data.weight12(o)
        for lay, gl in g.groupby("layer"):
            sid = gl.sid.to_numpy(); qf = gl[qc].to_numpy()
            y = data.Y[sid, t]
            L = pinball(np.nan_to_num(y), qf) / np.where(sc[sid] > 0, sc[sid], 1)
            win = data.window[sid, t]
            for label, m in (("excl_open", ok[sid]), ("incl_open", ok_all[sid]),
                             ("excl_open_excl_window", ok[sid] & ~win), ("incl_open_excl_window", ok_all[sid] & ~win)):
                w = w12[sid] * m
                if w.sum() == 0:
                    continue
                rows.append(dict(o=o, h=h, t=t, year=data.months[t].year, layer=lay, set=label,
                                 loss=float((w * L)[m].sum() / w.sum()), n=int(m.sum())))
    return pd.DataFrame(rows)


def block_bootstrap(diff_by_month, n=1000, block=3, seed=20261128):
    d = np.asarray(diff_by_month); k = len(d); rng = np.random.default_rng(seed)
    wins = 0
    for _ in range(n):
        st = rng.integers(0, k - block + 1, size=int(np.ceil(k / block)))
        idx = np.concatenate([np.arange(s, s + block) for s in st])[:k]
        wins += d[idx].mean() > 0
    return wins / n
