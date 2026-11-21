"""Generate the clearly labeled SAMPLE (synthetic) monthly demand series.
Trend + 12-month seasonality + noise, fixed seed so it is reproducible."""
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
