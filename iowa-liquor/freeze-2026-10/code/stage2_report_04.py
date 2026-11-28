"""Assemble 04-test-2025.md from the files s2eval test2025 wrote (no score is recomputed here).
Usage: python report_04.py <base> <checkpoint path>"""
import sys
from pathlib import Path
import pandas as pd

base = Path(sys.argv[1]); dst = Path(sys.argv[2]); s2 = base / "stage2"
L = []; w = L.append
lt = pd.read_csv(s2 / "layer_tests_2025.csv"); mt = pd.read_csv(s2 / "metric_2025.csv")
cov = pd.read_csv(s2 / "coverage_2025.csv"); fs = pd.read_csv(s2 / "flagged_scores_2025.csv", dtype={"series_id": str})
bk = pd.read_csv(s2 / "unit_breaks_2025_26.csv", dtype={"item_no": str})
w("# Checkpoint 04: the 2025 test (protocol 1.10 sections 5, 7, 9). STOP before 2026"); w("")
w("Run once (`s2eval.py . test2025`, Nov 28 2026), after tuning and every refit were fixed (checkpoint 03). This is the first "
  "read of any 2025 score. 2026 has not been run; `test2026` refuses to start without `ruling-04.md`.")
w(""); w("## Layer rule (section 9: 2% or more AND positive in at least 90% of 1,000 block-bootstrap resamples)"); w("")
w("| step | simpler loss | complex loss | gain | bootstrap share positive | result |"); w("|---|---:|---:|---:|---:|---|")
for r in lt.itertuples():
    w(f"| {r.complex} vs {r.simple} | {r.simple_loss:.4f} | {r.complex_loss:.4f} | {r.gain_pct:+.2f}% | {100 * r.boot_share:.1f}% | {'passes' if r.passes else 'fails (gain under 2%)'} |")
w(""); w("**Chosen layer: c** (equal-weight average of the per-series statistical pool and the tree model, uncalibrated). "
         "Layer d (c with conformal calibration) is 1.90% better with every resample positive, but under the 2% margin, so c stays.")
w(""); w("## Product-level selection metric on 2025 (WSPL)"); w("")
x = mt[mt.set.isin(["excl_open", "excl_open_excl_window", "incl_open"])].groupby(["set", "layer", "h"]).loss.mean().unstack("h")
x["mean h1-3"] = x.mean(axis=1)
w("| set | layer | h1 | h2 | h3 | mean h1-3 |"); w("|---|---|---:|---:|---:|---:|")
for (st, lay), r in x.iterrows():
    w(f"| {st} | {lay} | {r[1]:.4f} | {r[2]:.4f} | {r[3]:.4f} | {r['mean h1-3']:.4f} |")
w(""); w("The unit_change_window months are all in 2023, so leaving them out changes 2025 only in the fourth decimal (one 2025 window "
         "item-month, 38449 in Dec 2025). No open handover falls in a 2025 target month, so incl_open equals excl_open.")
w(""); w("## Coverage in 2025, dollar-weighted (section 5: 90% range 85-95, 50% range 44-56; intermittent and new: floors 85 and 44 only)"); w("")
c = cov.groupby(["period", "layer", "cls"])[["in90", "in50", "above95", "below05"]].mean().mul(100).reset_index()
w("| period | layer | class | in 90% | in 50% | above q95 | below q05 |"); w("|---|---|---|---:|---:|---:|---:|")
for r in c[c.layer.isin(["c", "d"])].itertuples():
    w(f"| {r.period} | {r.layer} | {r.cls} | {r.in90:.1f} | {r.in50:.1f} | {r.above95:.1f} | {r.below05:.1f} |")
pa = c[c.cls == "all"]
w(""); w("Pooled, every layer: " + "; ".join(f"{r.period} {r.layer} {r.in90:.1f}/{r.in50:.1f}" for r in pa.itertuples()) + " (in 90% / in 50%).")
w(""); w("### Reading against section 5")
w("- **Chosen layer c fails the coverage check**: pooled 50% coverage 56.8% (band 44-56), regular class 58.7%; intermittent 79.3% / 28.3% "
  "and new 59.5% / 33.9% are under both floors. Same in each half year (H1 56.1%, H2 57.4% pooled 50%), so it is not a first-half-only miss.")
w("- Layer d passes pooled (91.0 / 49.2) and regular (91.4 / 49.6), and the new-class floors (86.2 / 49.1); its intermittent 50% coverage, 40.9%, is under the 44% floor.")
w("- Section 5 says a fail allows one named retry (calibration window 12 -> 24 months), and if that also fails \"the uncalibrated "
  "ensemble is published with its measured coverage stated\"; \"a fail never picks a model\". Layer c already is the uncalibrated "
  "ensemble, so as written the outcome is: publish c with the coverage above stated. The retry changes only layer d, which the "
  "layer rule did not pick.")
w("- **Not done, waiting for the ruling**: I have not run the 24-month retry (it rebuilds the layers and rereads 2025 scores), and "
  "I have not changed the layer. Question for the design thread: publish c with its measured coverage (as written), or something else?")
w(""); w("## Scored separately (87035, 28081)"); w("")
g = fs.groupby(["series_id", "layer"]).agg(scaled_pinball=("scaled_pinball", "mean"), share=("share_of_trailing_dollars", "mean")).reset_index()
w("| series | layer | mean scaled pinball 2025 | share of trailing-12 dollars |"); w("|---|---|---:|---:|")
for r in g.itertuples():
    w(f"| {r.series_id} | {r.layer} | {r.scaled_pinball:.4f} | {100 * r.share:.3f}% |")
w(""); w(f"## Unit breaks inside 2025-26 (beside the score): {len(bk)}"); w("")
w("| item | month | pack before | pack after | factor | action | outcome | t12 $ |"); w("|---|---|---:|---:|---:|---|---|---:|")
for r in bk.itertuples():
    w(f"| {r.item_no} | {str(r.month)[:7]} | {r.pack_old} | {r.pack_new} | {r.factor:.4g} | {r.action} | {r.outcome} | {r.usd_t12:,.0f} |")
w(""); w("## Checks")
w("- Independent recompute from `layers.parquet` (scratch script, own pinball, mask and weights): 2025 h1 metric c 0.2204, d 0.2165; "
  "pooled h1 coverage c 90.9 / 57.4, d 90.9 / 50.1. All match the s2eval files.")
w("- `chosen_layer.json` now says c. The live files and level bottom-up sums were built on the fallback b and are rebuilt after the ruling.")
w("- Not done yet: the 2026 test (once, after this ruling), the live forecast refit on the chosen layer, the freeze package and manifest.")
dst.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"{dst.name}: {len(L)} lines")
