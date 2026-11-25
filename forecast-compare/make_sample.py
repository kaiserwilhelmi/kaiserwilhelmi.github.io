"""Generate the clearly labeled SAMPLE (synthetic) monthly series, fixed seeds so they are reproducible.
SAMPLE_demand: trend + 12-month seasonality + noise.
SAMPLE_spares: spare-part demand with many zero months (an order in about 40% of months, sizes
1 to ~15), with orders becoming rarer in the last two years as the part ages."""
import csv, math, random
random.seed(42)
rows = []
for i in range(106):  # Jan 2018 .. Oct 2026, same span as the FRED series
    y, mth = 2018 + i // 12, i % 12 + 1
    level = 1200 + 6.5 * i
    season = 180 * math.sin(2 * math.pi * (mth - 3) / 12) + 90 * (mth in (11, 12))
    units = round(level + season + random.gauss(0, 70))
    rows.append((f"{y}-{mth:02d}-01", units))
with open("data/SAMPLE_demand.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["date", "value"]); w.writerows(rows)

random.seed(7)
rows = []
for i in range(106):
    y, mth = 2018 + i // 12, i % 12 + 1
    p = 0.4 if i < 82 else 0.22
    units = (1 + round(math.exp(random.gauss(math.log(4), 0.6)))) if random.random() < p else 0
    rows.append((f"{y}-{mth:02d}-01", units))
with open("data/SAMPLE_spares.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["date", "value"]); w.writerows(rows)
