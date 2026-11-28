"""Brand map (F2), keyed on series_id. A brand is the brand family a supplier sells under (Crown Royal covers its
flavours and sizes). Assignment: the normalised description (upper case, apostrophes and periods removed, spaces
collapsed) is matched to the longest brand prefix in BRANDS below, at a word boundary. The prefix list was written by
hand from the 400 series with the most trailing-12-month dollars (about 71% of dollars); those 400 are reported as
"hand-checked", the rest that match as "rule only", and the rest as "unassigned".
Also runs the units check by brand (Addendum 4c): liters from bottles x ml against liters with the clean sibling
factor for carriers (only factors that are whole numbers matching a plausible pack; listed in CARRIER_FACTOR).
Usage: python brand_map.py <base>"""
import re, sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd

# prefix -> brand. Order does not matter; the longest matching prefix wins.
BRANDS = {
    "TITOS": "Tito's", "CAPTAIN MORGAN": "Captain Morgan", "BLACK VELVET": "Black Velvet", "FIREBALL": "Fireball",
    "CROWN ROYAL": "Crown Royal", "PATRON": "Patron", "FRIS": "Fris", "PLATINUM 7X": "Platinum 7X",
    "JACK DANIELS": "Jack Daniel's", "GENTLEMAN JACK": "Jack Daniel's", "JAMESON": "Jameson", "SMIRNOFF": "Smirnoff",
    "BUFFALO TRACE": "Buffalo Trace", "HAWKEYE": "Hawkeye", "CEDAR RIDGE": "Cedar Ridge", "MAKERS MARK": "Maker's Mark",
    "MAKERS 46": "Maker's Mark", "DON JULIO": "Don Julio", "RUMPLE MINZE": "Rumple Minze", "MCCORMICK": "McCormick",
    "SVEDKA": "Svedka", "HENNESSY": "Hennessy", "WOODFORD RESERVE": "Woodford Reserve", "ABSOLUT": "Absolut",
    "MALIBU": "Malibu", "TORTILLA": "Tortilla", "JOSE CUERVO": "Jose Cuervo", "JIM BEAM": "Jim Beam",
    "SEAGRAMS 7 CROWN": "Seagram's 7 Crown", "SEAGRAMS VO": "Seagram's VO", "KIRKLAND": "Kirkland Signature",
    "ADMIRAL NELSON": "Admiral Nelson", "BAILEYS": "Baileys", "BULLEIT": "Bulleit", "REVELTON": "Revelton",
    "BLANTONS": "Blanton's", "DR MCGILLICUDDYS": "Dr. McGillicuddy's", "JAGERMEISTER": "Jagermeister",
    "THE ORIGINAL PICKLE SHOT": "The Original Pickle Shot", "MONTEZUMA": "Montezuma", "COINTREAU": "Cointreau",
    "CASAMIGOS": "Casamigos", "GREY GOOSE": "Grey Goose", "BACARDI": "Bacardi", "99": "99 Brand",
    "EVAN WILLIAMS": "Evan Williams", "BLUE OX": "Blue Ox", "KAHLUA": "Kahlua", "BARTON": "Barton",
    "TANQUERAY": "Tanqueray", "ELIJAH CRAIG": "Elijah Craig", "TEREMANA": "Teremana", "FOUR ROSES": "Four Roses",
    "RED STAG": "Red Stag", "ESPOLON": "Espolon", "MEMBERS MARK": "Member's Mark", "KNOB CREEK": "Knob Creek",
    "WINDSOR CANADIAN": "Windsor Canadian", "LICOR 43": "Licor 43", "RUMCHATA": "RumChata", "ST GERMAIN": "St-Germain",
    "BASIL HAYDEN": "Basil Hayden", "JUAREZ": "Juarez", "RICH & RARE": "Rich & Rare", "ANGELS ENVY": "Angel's Envy",
    "GRANGALA": "GranGala", "OLE SMOKY": "Ole Smoky", "CANADIAN CLUB": "Canadian Club", "KETEL ONE": "Ketel One",
    "KESSLER": "Kessler", "LALO": "Lalo", "HA WELLER": "Weller", "WELLER": "Weller", "FIVE OCLOCK": "Five O'Clock",
    "NIKOLAI": "Nikolai", "DEKUYPER": "DeKuyper", "SKREWBALL": "Skrewball", "DISARONNO": "Disaronno", "1800": "1800",
    "FLEISCHMANNS": "Fleischmann's", "TEMPLETON": "Templeton", "HENDRICKS": "Hendrick's", "CLASE AZUL": "Clase Azul",
    "HORNITOS": "Hornitos", "WILD TURKEY": "Wild Turkey", "OLMECA ALTOS": "Olmeca Altos", "CAZADORES": "Cazadores",
    "FIVE STAR": "Five Star", "DEEP EDDY": "Deep Eddy", "NEW AMSTERDAM": "New Amsterdam", "BUCHANAN": "Buchanan's",
    "BUCHANANS": "Buchanan's", "OLD FITZGERALD": "Old Fitzgerald", "TEN HIGH": "Ten High", "PENDLETON": "Pendleton",
    "CANADIAN LTD": "Canadian LTD", "PARAMOUNT": "Paramount", "PAUL MASSON": "Paul Masson", "BOOKERS": "Booker's",
    "JOHNNIE WALKER": "Johnnie Walker", "BOMBAY": "Bombay", "OLD FORESTER": "Old Forester",
    "RIDGEMONT RESERVE 1792": "1792", "1792": "1792", "TRAVELLER": "Traveller", "UV": "UV", "EAGLE RARE": "Eagle Rare",
    "BUZZBALLZ": "BuzzBallz", "EXOTICO": "Exotico", "CORAZON": "Corazon", "GLENLIVET": "Glenlivet",
    "GRAND MARNIER": "Grand Marnier", "LUNAZUL": "Lunazul", "DEWARS": "Dewar's", "ASTRAL": "Astral",
    "CHI-CHIS": "Chi-Chi's", "REMY MARTIN": "Remy Martin", "CALIBER": "Caliber", "FROST TRAIL": "Frost Trail",
    "SHANKYS": "Shanky's", "EVERCLEAR": "Everclear", "OLD CROW": "Old Crow", "SOUTHERN COMFORT": "Southern Comfort",
    "DUSSE": "D'Usse", "SAINTS N SINNERS": "Saints N Sinners", "CALYPSO": "Calypso", "CHAMBORD": "Chambord",
    "GOTCHA": "Gotcha", "PINNACLE": "Pinnacle", "CARAVELLA": "Caravella", "MR BOSTON": "Mr. Boston",
    "LAUDERS": "Lauder's", "CORRALEJO": "Corralejo", "HEAVEN HILL": "Heaven Hill", "MILAGRO": "Milagro",
    "PHILLIPS": "Phillips", "CAMPARI": "Campari", "E & J": "E&J", "REBEL": "Rebel", "APEROL": "Aperol",
    "PIONEERING THE SPIRIT OF IOWA": "Cedar Ridge", "EL MAYOR": "El Mayor", "GRAN PATRON": "Patron",
}
# leading order-type tags the state puts before the brand (special order, barrel pick, hand-selected; Addendum 5
# reverse check); stripped before matching, repeatedly ("HA BP CROWN ROYAL ...")
TAGS = ("SOOH ", "HA ", "BP ")
# series reviewed by hand after the first 400 (Addendum 5 / decision 49, Nov 28 2026): the rule-only series of the
# top-20 brands and the reverse-check series, all read and confirmed. The list is a file made from the reviewed CSVs.
HAND_EXTRA_FILE = "hand_checked_extra_2026-11-28.csv"
TOP_N_HAND = 400
# carriers with a clean whole-number factor (decision 47 table, design note): Tito's 100ml 38449 = 12 x $10.50;
# 99 Cherries mini 84155 = 9 x $9.00. Decision 48: Jameson 15621 and 99 Bananas 84172 are 12 x 50ml carriers
# throughout (bottles and price continuous across the 2019 ml change 600 -> 50); factor 12 applies only to rows
# recorded at 50ml (rows at 600ml already carry the carrier volume). (item, factor, ml the factor applies to or None)
# Withdrawn by decision 51 (liters tiers, stage2/units_tiers.py), which also withdraws the x9 on 84155 and replaces
# the Addendum 4 1% / 2% test. Kept as an empty list so older scripts that import it still run.
CARRIER_FACTOR = []


def norm(s):
    s = re.sub(r"[.'’]", "", str(s).upper())
    return re.sub(r"\s+", " ", s).strip()


KEYS = sorted(BRANDS, key=len, reverse=True)


def brand_of(desc):
    d = norm(desc)
    stripped = True
    while stripped:
        stripped = False
        for tg in TAGS:
            if d.startswith(tg):
                d = d[len(tg):]; stripped = True
    for k in KEYS:
        if d == k or d.startswith(k + " "):
            return BRANDS[k]
    return None


if __name__ == "__main__":
    base = Path(sys.argv[1]); out = base / "stage2"; out.mkdir(exist_ok=True)
    con = duckdb.connect(str(base / "stage1" / "iowa_liquor.duckdb"), read_only=True)
    s = con.execute('''
    WITH t AS (SELECT series_id, SUM(dollars_retail) AS d12, SUM(bottles) AS b12 FROM series_month
               WHERE month_start > (SELECT MAX(month_start) FROM series_month) - INTERVAL 12 MONTH GROUP BY 1)
    SELECT t.series_id, r.d AS description, r.ml, v.current_vendor_name AS vendor, t.d12, t.b12
    FROM t JOIN item_series r ON r.item_no = t.series_id LEFT JOIN item_vendor v ON v.item_no = t.series_id''').df()
    s = s.sort_values("d12", ascending=False).reset_index(drop=True)
    s["brand"] = s.description.map(brand_of)
    hf = out / HAND_EXTRA_FILE
    extra = set(pd.read_csv(hf, dtype={"series_id": str}).series_id) if hf.exists() else set()
    s["brand_source"] = ["hand-checked" if b is not None and (i < TOP_N_HAND or sid in extra) else "rule only"
                         if b is not None else "unassigned" for i, (b, sid) in enumerate(zip(s.brand, s.series_id))]
    print(f"hand-checked extra list: {len(extra)} series" + (f" ({hf.name})" if extra else " (no file)"))
    s.to_csv(out / "brand_map.csv", index=False)
    tot = s.d12.sum()
    cov = s.groupby("brand_source").agg(series=("series_id", "size"), dollars=("d12", "sum"))
    cov["pct_dollars"] = (100 * cov.dollars / tot).round(2)
    print("brand map coverage (trailing-12 dollars):"); print(cov.to_string())
    miss = s.head(TOP_N_HAND)[s.head(TOP_N_HAND).brand.isna()]
    print("top-400 series with no brand:", miss[["series_id", "description"]].values.tolist()[:40], f"({len(miss)} in all)")
    tb = s.dropna(subset=["brand"]).groupby("brand").agg(dollars=("d12", "sum"), series=("series_id", "size"),
                                                          vendors=("vendor", lambda v: "; ".join(sorted(set(map(str, v))))[:60]))
    tb = tb.sort_values("dollars", ascending=False)
    tb["pct"] = (100 * tb.dollars / tot).round(2)
    tb.head(20).to_csv(out / "top20_brands.csv")
    print("top 20 brands:"); print(tb.head(20)[["dollars", "pct", "series", "vendors"]].round(0).to_string())
    print("units: decision 48 carrier table withdrawn; liters tiers are built by units_tiers.py (decision 51)")
    sys.exit(0)
    # (the decision 48 units check below is no longer run)
    con.register("bm", s[["series_id", "brand"]])
    con.register("cf", pd.DataFrame(CARRIER_FACTOR, columns=["item_no", "k", "only_ml"]))
    u = con.execute('''
    SELECT bm.brand, SUM(l.sales_bottles * l.bottle_volume_ml) / 1e3 AS liters_bottles_x_ml,
           SUM(l.sales_bottles * l.bottle_volume_ml * COALESCE(cf.k, 1)) / 1e3 AS liters_corrected
    FROM sales l JOIN item_series i USING (item_no) JOIN bm ON bm.series_id = i.series_id
    LEFT JOIN cf ON cf.item_no = l.item_no AND (cf.only_ml IS NULL OR cf.only_ml = l.bottle_volume_ml)
    WHERE l.sales_bottles > 0 AND l.order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH
    GROUP BY 1''').df()
    u["pct_diff"] = 100 * (u.liters_corrected / u.liters_bottles_x_ml - 1)
    st = u[["liters_bottles_x_ml", "liters_corrected"]].sum()
    u.to_csv(out / "units_check_by_brand.csv", index=False)
    ut = u[u.brand.isin(tb.head(20).index)].sort_values("pct_diff", ascending=False)
    print(f"units: state liters bottles x ml {st.liters_bottles_x_ml:,.0f} | corrected {st.liters_corrected:,.0f} "
          f"({100 * (st.liters_corrected / st.liters_bottles_x_ml - 1):+.3f}%)")
    print("top-20 brands, liters (thousand) and pct diff:"); print(ut.assign(l0=ut.liters_bottles_x_ml / 1e3, l1=ut.liters_corrected / 1e3)[["brand", "l0", "l1", "pct_diff"]].round(3).to_string(index=False))
    over = (abs(st.liters_corrected / st.liters_bottles_x_ml - 1) > 0.01) or (ut.pct_diff.abs() > 2).any()
    print("Addendum 4c:", "APPLY units table (state > 1% or a top-20 brand > 2%)" if over else "page note only")
    ut.to_csv(out / "units_check_top20.csv", index=False)
    it = con.execute('''
    SELECT l.item_no, l.bottle_volume_ml AS ml, CASE WHEN cf.only_ml IS NULL OR cf.only_ml = l.bottle_volume_ml
               THEN cf.k ELSE 1 END AS factor, SUM(l.sales_bottles) AS bottles,
           SUM(l.sales_bottles * l.bottle_volume_ml) / 1e3 AS liters_before,
           SUM(l.sales_bottles * l.bottle_volume_ml * CASE WHEN cf.only_ml IS NULL OR cf.only_ml = l.bottle_volume_ml
               THEN cf.k ELSE 1 END) / 1e3 AS liters_after
    FROM sales l JOIN cf ON cf.item_no = l.item_no
    WHERE l.sales_bottles > 0 AND l.order_date > (SELECT MAX(order_date) FROM sales) - INTERVAL 12 MONTH
    GROUP BY 1, 2, 3 ORDER BY 1, 2''').df()
    it["gain"] = it.liters_after - it.liters_before
    it["check"] = it.bottles * it.ml * (it.factor - 1) / 1e3
    it.to_csv(out / "units_items_t12.csv", index=False)
    print("carrier items, trailing 12:"); print(it.round(1).to_string(index=False))
    pd.DataFrame(CARRIER_FACTOR, columns=["item_no", "pack_factor", "applies_to_ml"]).assign(
        rule="liters per recorded bottle = bottle_volume_ml x pack_factor on rows at applies_to_ml (blank = all rows); "
             "bottles and dollars unchanged").to_csv(out / "units_table.csv", index=False)
