"""Assemble 03-tuning.md (protocol 6a, rulings 01d-amend, 01e, 01e-amend, 02-resume). Read-only on results; 2023-24
targets only (no 2025 or 2026 score is read). Usage: python report_03.py <base> <checkpoint path>"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from trials_read import read_trials

base = Path(sys.argv[1]); dst = Path(sys.argv[2]); s2 = base / "stage2"
L = []; w = L.append
t = read_trials(s2 / "tree" / "trials.csv"); cfg = json.load(open(s2 / "tree" / "chosen_config.json"))
t0 = t[t.trial == "featureset_base"].iloc[-1]
P = ["num_leaves", "min_data_in_leaf", "learning_rate", "feature_fraction", "bagging_fraction", "lambda_l2"]

w("# Checkpoint 03: tuning (protocol 1.10 section 6a)"); w("")
w("All choices below use 2023 and 2024 targets only. No 2025 or 2026 score has been computed or read.")
w(""); w("**Summary.** Tree: tuned settings adopted (trial 3, +5.96%, better in 2023 and in 2024), base features, Tweedie 1.1. "
         "Stat members: tuned per class (SBA/TSB alpha 0.3, ADIDA 2 for intermittent). No restarts. All members and tree fits "
         "were refit with these settings (stat 27 min, tree 46 min); verify_stage1 all OK. Level ranges built and calibrated. "
         "Items 2a, 2b, 7 with 11, and 13 are reported below and the tiers were rerun, so the liters hold lifts (ruling-01e-amend "
         "item 15). Next: the 2025 test and checkpoint 04, then a stop before 2026.")
w("")
w("## Tree model (LightGBM, one model per horizon and quantile)"); w("")
fs = t[t.trial.str.startswith("featureset")]
w("Feature set, under the starting settings (lower is better, three-quantile proxy, mean of h1-h3):"); w("")
w("| feature set | proxy | 2023 | 2024 | excl. window months |"); w("|---|---:|---:|---:|---:|")
for r in fs.itertuples():
    w(f"| {r.feature_set} | {r.score_h1_3:.4f} | {r.score_2023:.4f} | {r.score_2024:.4f} | {r.score_excl_window:.4f} |")
w(""); w(f"Chosen: **{cfg['feature_set']}**. Then {cfg['trials_run']} random trials on all series (seed 20261127), each fit "
         "through Dec 2022 (rounds chosen on 2023 targets, early stopping, patience 100, cap 2000) and reused through Dec 2023.")
w(""); w("| trial | " + " | ".join(P) + " | proxy | 2023 | 2024 | excl. window | seconds | models at 2000 |")
w("|---|" + "---:|" * (len(P) + 6))
rnd = t[t.trial.str.fullmatch(r"\d+")].copy(); rnd["n"] = rnd.trial.astype(int)
for r in pd.concat([fs[fs.feature_set == cfg["feature_set"]].assign(n=0), rnd]).itertuples():
    cap = sum(v >= 2000 for v in json.loads(r.rounds).values())
    lab = "0 (start)" if r.n == 0 else str(r.n)
    b = "**" if r.n == cfg["best_trial"] else ""
    w(f"| {b}{lab}{b} | " + " | ".join(f"{getattr(r, p):.4g}" for p in P)
      + f" | {b}{r.score_h1_3:.4f}{b} | {r.score_2023:.4f} | {r.score_2024:.4f} | {r.score_excl_window:.4f} | {r.seconds:.0f} | {cap} of 9 |")
best = rnd.loc[rnd.score_h1_3.idxmin()]
w(""); w(f"- Best: trial {int(best.n)}, proxy {best.score_h1_3:.4f} vs start {t0.score_h1_3:.4f}: gain "
         f"**{100 * (1 - best.score_h1_3 / t0.score_h1_3):.2f}%** (rule: 1% or more). 2023 {best.score_2023:.4f} vs {t0.score_2023:.4f}, "
         f"2024 {best.score_2024:.4f} vs {t0.score_2024:.4f}: better in both years. **Adopted: {cfg['adopted_tuned']}** "
         "(checked a second time from trials.csv by `code\\stage2\\trials_read.py`).")
w("- Chosen settings: " + ", ".join(f"{k} {v:.4g}" for k, v in cfg["settings"].items()) + ".")
tw = t[t.trial.str.startswith("tweedie")]
w("- Tweedie power for the mean model (scaled squared error of the mean, 2023-24, chosen settings): "
  + "; ".join(f"{r.trial.split('_')[1]}: {r.mean_sq_error:.4f}" for r in tw.itertuples())
  + f". Chosen **{cfg['tweedie_power']}**, the lowest value in the grid {{1.1, 1.3, 1.5, 1.7}}. The grid is fixed, so it is not extended.")
w("- Restarts: none. All 40 trials, both feature-set runs and the 4 Tweedie runs ran in one uninterrupted job "
  "(ruling-02-resume item 3). The resume code was in place and was not needed.")
# rounds at cap
rf = json.load(open(s2 / "tree" / "rounds_fixed.json"))
ncap = sum(v >= 2000 for v in rf.values()); near = sum(v >= 1900 for v in rf.values())
w(f"- **Rounds at the cap (ruling-01e-amend item 3)**: in the final tuned fit through Dec 2022 (rounds fixed for every later fit), "
  f"**{ncap} of {len(rf)}** models (horizon x quantile/mean) stopped at 2,000 rounds; {near} at 1,900 or more. Per model: "
  + ", ".join(f"{k} {v}" for k, v in rf.items()) + ". The cap was not raised.")
tri_cap = sum(sum(v >= 2000 for v in json.loads(r.rounds).values()) for r in rnd.itertuples())
w(f"  Across the 40 trials, {tri_cap} of {9 * len(rnd)} three-quantile models stopped at the cap.")

# stat members
w(""); w("## Statistical members, per demand class (section 6a grids, origins 2022-12..2024-11)"); w("")
sc = pd.read_csv(s2 / "stat_tune_choices.csv")
w("| class | member | start | best | gain | adopted (1% rule) | used |"); w("|---|---|---|---|---:|---|---|")
for r in sc.itertuples():
    w(f"| {r.cls} | {r.member} | {r.start} | {r.best} | {r.gain_pct:.2f}% | {r.adopted} | {r.chosen} |")
w(""); w("- For SBA and TSB the chosen alpha 0.3 is the top of the fixed grid {0.05, 0.1, 0.2, 0.3}. The grid is not extended. "
         "Detail per grid point: `stage2\\stat_tune_results.csv`.")

# scores
w(""); w("## Selection metric on 2023-24 targets: baseline vs tuned (WSPL, excl. open handovers and separately scored items)"); w("")
new = pd.read_csv(s2 / "metric_summary_2023_24.csv"); old = pd.read_csv(s2 / "baseline" / "metric_summary_2023_24.csv")
k = ["set", "year", "layer"]
m = new.merge(old, on=k, suffixes=("", "_base"))
w("| set | year | layer | h1 | h2 | h3 | mean h1-3 | baseline mean | change |"); w("|---|---|---|---:|---:|---:|---:|---:|---:|")
for r in m.itertuples():
    w(f"| {r.set} | {r.year} | {r.layer} | {getattr(r, '_4'):.4f} | {getattr(r, '_5'):.4f} | {getattr(r, '_6'):.4f} | "
      f"{r.mean_h1_3:.4f} | {r.mean_h1_3_base:.4f} | {100 * (r.mean_h1_3 / r.mean_h1_3_base - 1):+.2f}% |")
ap = pd.read_csv(base / "stage1" / "unit_breaks_applied.csv", dtype={"item_no": str})
isr = pd.read_csv(base / "stage1" / "item_series.csv", dtype={"item_no": str, "series_id": str}).set_index("item_no").series_id
wi = sorted({isr.get(i, i) for i in ap[ap.outcome == "restated"].item_no})
w(""); w(f"Set `*_excl_window` leaves out the unit_change_window item-months (break month and the next) of the {len(wi)} restated "
         f"series: {', '.join(wi)}. The selection metric itself keeps all months in (ruling-01d-amend item 1). "
         "The window months all fall in 2023, so the 2024 rows are the same in both sets. These are the years the settings "
         "were chosen on, so the changes against the baseline are optimistic; the 2025 test is the first honest read. "
         "Layers: a = seasonal naive, b = per-series pool, c = pool plus tree, d = layer c with ranges calibrated in time order. "
         "The layer is chosen at the 2025 test (section 7); until then the fallback is b. Two cells (excl_open, 2024, h1, "
         "layers b and c) were recomputed independently from layers.parquet: 0.2392 and 0.2269, matching.")

# watch list
w(""); w("## Watch list: 84222 and 84226 (ruling-01e-amend item 9)"); w("")
wl = pd.read_csv(s2 / "watch_list_scores.csv", dtype={"series_id": str})
w("| series | layer | year | scaled pinball, all months | excl. window months | months with / without |"); w("|---|---|---|---:|---:|---|")
for r in wl.itertuples():
    w(f"| {r.series_id} | {r.layer} | {r.year} | {r.all_months:.4f} | {r.excl_window:.4f} | {r.n_all} / {r.n_excl} |")
w(""); w("The \"all months\" figures include the May-June 2023 window months (note per ruling-01d-amend item 1).")

# June diagnostic
w(""); w("## June diagnostic (ruling-01d-amend item 2, report only)"); w("")
jd = pd.read_csv(s2 / "june_diagnostic.csv", dtype={"series_id": str})
w(f"The ruling names 13 99 minis with a May 2023 break; the data has **{len(jd)}** restated 99 minis with a May 2023 break "
  "(976365 was cut, not restated), so all of them are shown. Fit: additive-season ETS through 2024-12 on per-order-day "
  "values (items: restated bottles; categories: dollars, decision 52). June index = 1 + centred June seasonal state / mean "
  "2024 level. Items with under 36 months are marked: protocol section 6 would not fit a seasonal form for them.")
w(""); w("| series | category | months | item June index | category June index | item / category |"); w("|---|---|---:|---:|---:|---:|")
for r in jd.sort_values("ratio", ascending=False).itertuples():
    w(f"| {r.series_id} | {r.category} | {r.months_history}{' *' if r.months_history < 36 else ''} | {r.item_june_index:.3f} | "
      f"{r.category_june_index:.3f} | {r.ratio:.3f} |")
w(""); w(f"Median item index {jd.item_june_index.median():.3f} vs category {jd.category_june_index.median():.2f}. A raw check "
         "(June per-order-day bottles over that year's mean) gives June 2023 at 1.16-2.19 for every item, against 0.78-1.48 in June 2024. "
         "Part of the items' June lift sits in the June 2023 window month. No change to fitting (ruling-01e-amend item 5).")

# levels
w(""); w("## Level ranges (protocol section 2, ruling-01e-amend item 4)"); w("")
lv = pd.read_parquet(s2 / "levels_forecasts.parquet", columns=["level", "o", "h", "calibrated"])
c = lv.groupby("level").calibrated.agg(["mean", "size"])
w("Direct ETS ranges for state, category and brand are built and calibrated in time order (split conformal on scaled errors, "
  "past targets only; window 12 months, 36 for the state and for categories with fewer than 19 errors). Share of rows calibrated: "
  + "; ".join(f"{i} {100 * r['mean']:.1f}% of {int(r['size']):,}" for i, r in c.iterrows())
  + ". Rows that are not calibrated are published as totals with no range.")
lvf = pd.read_parquet(s2 / "levels_forecasts.parquet", columns=["level", "o", "outside_own_50", "calibrated"])
last = lvf[lvf.o == lvf.o.max()]
w(f"- At the last origin (2026-10), the bottom-up sum falls outside the level's own direct 50% range in "
  f"{int(last.outside_own_50.sum())} of {len(last)} level-horizons ("
  + ", ".join(f"{k} {int(v.outside_own_50.sum())} of {len(v)}" for k, v in last.groupby("level"))
  + "). Both figures are shown and the row is flagged (section 2). The bottom-up sum uses the fallback layer b until the 2025 test.")

# units
w(""); w((s2 / "report_03_units.md").read_text(encoding="utf-8"))
dst.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"{dst.name}: {len(L)} lines")
