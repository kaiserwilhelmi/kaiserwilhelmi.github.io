"""Writes stage2/hand_checked_extra_2026-11-28.csv: the 513 rule-only series and 15 reverse-check series I read by
hand on Nov 28 2026 (decision 49 follow-up). Usage: python make_hand_extra.py <base>"""
import sys
from pathlib import Path
import pandas as pd
out = Path(sys.argv[1]) / "stage2"
a = pd.read_csv(out / "addendum5_rule_only_for_hand_check.csv", dtype={"series_id": str}).series_id
r = pd.read_csv(out / "addendum5_reverse_check.csv", dtype={"series_id": str}).series_id
ids = pd.Series(sorted(set(a) | set(r)), name="series_id")
ids.to_frame().to_csv(out / "hand_checked_extra_2026-11-28.csv", index=False)
print(f"hand-checked extra: {len(set(a))} rule-only + {len(set(r))} reverse-check = {len(ids)} series")
