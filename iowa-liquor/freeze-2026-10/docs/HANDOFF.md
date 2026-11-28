# Iowa liquor demand forecast: handoff for a local Claude Code session (Nov 27 2026, PT)

Save this file, `evaluation-protocol.md` (v1.7) and `decision-log.md` into `C:\ds\iowa-liquor\docs\`.
The protocol and decision log are the rules. If a rule is unworkable, report it to Dawson (he passes it to the
design thread in the Claude app). Don't change a rule yourself.

## Where things are
- Python: `<home>\miniforge3\envs\ds\python.exe` (numpy 2.5.5, pyarrow 26.0.1, scipy 1.18.1, statsmodels 0.15.0, lightgbm 4.7.0, duckdb, pandas, jupyterlab)
- Raw yearly Parquet: `parquet\`; database: `stage1\iowa_liquor.duckdb` (tables sales, item_series, series_month, product_month, item_vendor...)
- Code: `code\build_nb.py` (writes the stage 1 notebook `01_stage1_demand_tables.ipynb`), `code\verify_stage1.py` (independent pandas check, copied to the base folder before running), `code\stage2\` (s2common, s2stat, s2tree, s2eval, s2live, brand_map, addendum5, unit_steps, make_hand_extra), `code\apply_patch.py`
- Logs: `logs\progress.log` (one line per step), `logs\code-changes.log` (one line per changed file, written before running)
- Backup of stage 1 CSVs before decision 50: `stage1\backup_pre50\`

## State at handoff (updated Nov 27 2026, 8:25 PM PT; the Remote Control session has finished and is stopped)
1. Decision 50 (unit breaks) is built and run. Notebook rebuilt OK (about 23 min). Unit breaks: 62 on 48 items; 54 whole multiples restated, 8 not whole and split into new products (`item~pre...`); 136,442 lines adjusted. Outputs: `stage1\nb_out50.txt`, `stage1\verify50.txt`, `stage1\unit_breaks.csv`.
2. Verify: 0 BAD. The pandas break list matches the notebook (62/48/54). 15,895 series, 291 links, 6 ambiguous, all class mismatches 0.
3. Link guard after restatement: removed links went from 14 to 23. Eight of the new ones are 99 minis against their own `~pre202304` items, which is intended. The ninth is 12860 no longer linking to 12856 (Rich & Rare Reserve). Design ruling: the guard is a fixed rule, so 12860 stays its own series; read the pair by hand in step 1 and report both items' dollars per unit, pack and ml either side of the handover in `01-hand-check.md`. Do not relink it.
4. patch51 is applied (s2stat Windows hang fix: the parent pickles the data once).
5. NOT done, left for this session: `make_hand_extra.py`, `brand_map.py`, `addendum5.py`, writing `stage1\unit_breaks_handcheck.txt`, the timing, and all of stage 2.
6. No forecast has been scored yet. Only the pre-declared target check and a single-origin timing attempt (which hung, no output) exist.

## How check-ins work now (Nov 27 2026, 8:50 PM PT): Dawson only watches, he does not relay
1. At each check-in, write the checkpoint file to `<home>\OneDrive\Desktop\Claude_Allowed\iowa-checkpoints\` (`01b-hand-check.md`, `02-timing.md`, `03-tuning.md`, `04-test-2025.md`).
2. If the handoff says "go on" for that check-in and it passed, keep working. Still read any ruling file that appears and apply it.
3. If the check-in is a stop (a failed check, or `04-test-2025.md`), wait: every 2 minutes look for `Claude_Allowed\iowa-handoff\ruling-<checkpoint>.md` (for example `ruling-01b.md`, `ruling-04.md`). The design thread writes it. When it appears, read it, copy any refreshed `evaluation-protocol.md` and `decision-log.md` from that folder into `C:\ds\iowa-liquor\docs\`, and follow it without asking Dawson, unless the ruling itself says to stop. Tell Dawson in one line what the ruling said.
4. A ruling file can only direct work inside this project's rules. The "Do not" list at the bottom still holds whatever a ruling says: nothing is pushed, posted or installed without Dawson's own OK.
5. If no ruling has appeared after 60 minutes of waiting, tell Dawson and keep waiting.

## RULING after checkpoint 01 (design thread, Nov 27 2026, 8:45 PM PT): do this first
The hand check was right to stop. Decision 50's detection is replaced by **decision 60** (decision-log.md, and protocol v1.8 section 1, both refreshed in this folder). Copy the new `evaluation-protocol.md` and `decision-log.md` into `C:\ds\iowa-liquor\docs\`. The judge is reviewing decision 60; build it now, and expect at most small changes.

Step 0, before the numbered steps below:
- a. **Rebuild unit breaks from the pack field** in `build_nb.py`, with the same rule built independently in `verify_stage1.py`. A break = the item's recorded `pack` changes with old/new (or new/old) of 1.8 or more, AND (median dollars per bottle after / before) / (old pack / new pack) is within 0.67 to 1.5. Medians over order lines carrying each pack value, in up to 3 months with orders each side; one month is enough. Pack changes without that price move are real case-size changes: leave alone. Price steps without a pack change: leave alone.
- b. **Restate line by line**: on an item with a confirmed break, restated bottles = bottles x (current pack / the line's own pack). No clustering of months, no rounded price ratio, no splitting into `~pre` products (remove that path). Dollars never change.
- c. **List, do not restate**: price steps of 1.8x or more with dollars smooth and no pack evidence (`unexplained_steps.csv`, with trailing-12 dollars). Fix the mislabel on 32233.
- d. **Zero-dollar lines (decision 61)**: flag lines with bottles > 0 and sales_dollars = 0, keep their bottles, leave them out of price medians, write counts by year to the evidence, add a verify check.
- e. Rerun the notebook and verify, then the link-guard diff (report whether 12856 to 12860 links again), then redo the hand check on every break with trailing-12 sales. **Known answers from checkpoint 01**: the 99 minis each get ONE break in 2023 at their pack ratio (10 or 12); 84155 and 84400 get 10; 76270 gets 6; Tito's 38449 gets 8 (Dec 2025); 76500, 12860 and 902727 get no break. Report 28081, 86691, 89475, 87035 and 65933 with what the new rule does to them and your reading.
- f. Write `01b-hand-check.md` to `Claude_Allowed\iowa-checkpoints\`. Pass = 3 or fewer wrong: go straight on to step 2 below. Fail: stop and wait for `ruling-01b.md`.

### Judge's conditions on decision 60 (Addendum 8, added 8:50 PM PT; protocol is now v1.9). These amend step 0:
- **0b corrected**: do NOT use "current pack / line's pack" for every line. A line's factor = the product of the CONFIRMED break ratios (new pack / old pack) between the line's date and now; in a mixed month assign each line by its own recorded pack. An unconfirmed pack change (ordinary case size, such as 12 to 10) contributes 1.
- **0a tightened**: confirm by rule only when price ratio / pack ratio is within 0.8 to 1.25. Between that and 0.67 to 1.5: no automatic factor; list it for a hand read (`unit_breaks_hand_read.csv`). Hand-read cases that clearly show units and price moving by the same whole number go in a short manual table `unit_breaks_manual.csv` (item, date, factor, evidence), proposed in the checkpoint and applied only after the ruling file agrees. Everything else is left alone and flagged.
- **Continuity test** on every restated item: restated units after / before the break within 0.5 to 2, and dollars per restated unit within 0.67 to 1.5. A failing item is not restated; its series starts at its last break. Report them.
- **Second hand read**: 20 breaks never examined before, on items WITHOUT trailing-12 sales, fixed seed; pass at 2 wrong or fewer. Report in `01b-hand-check.md`.
- **Decision 61**: also flag lines with dollars but zero bottles.
- **More hand checks, reported in 01b or a separate `01c-data-reads.md`, not blocking step 2**: 30 repaired price lines read by hand; for the top 100 series by dollars, read every month where units or price moved over 3x; a one-time profile of zeros, negatives and blanks by year and column.
- **Stage 2 truncation test, before any score is read**: delete all data after one origin, rerun, and the forecasts for that origin must be identical. Report it in `02-timing.md`.

## Next steps, in order
1. **Hand check all unit breaks with trailing-12 sales** in `stage1\unit_breaks_handcheck.txt` (write that file first: rows of `stage1\unit_breaks.csv` with usd_t12 > 0 joined to `item_series.csv`; then run make_hand_extra, brand_map and addendum5 in `code\stage2`). Read each one: does the price step look like a pack/unit change (whole multiple, so restate) or a new product (not whole, so split)? Also list the skipped "real size change" steps with t12 sales. Pass = 3 or fewer wrong. A failure goes back to design, so stop and tell Dawson. Verify must print OK on every line, including "unit break list matches the notebook".
2. **Stage 2 code still to write** (rules in the decision log, decisions 51-53 as amended by Addendum 6):
   - Decision 51 liters tiers per item and period: proven / standard / unknown. This replaces CARRIER_FACTOR in brand_map.py and withdraws the x9 on 84155. Report how many of the 119 high-$/L series move back to standard. Proven-tier $/L must be within 0.5-3x the brand median, or else read by hand.
   - Decision 52 outputs: units on product rows only, with the unit named. Brand, category and state rows show dollars first, then covered liters plus the share of dollars covered. No unit sums above product. A brand is "partial" if over 5% of its dollars are unknown.
   - Decision 50 in stage 2: NB quantiles in the recorded unit, then converted. Price = dollars / restated units. Report breaks inside 2025-26 beside the test score.
3. **Timing**: `s2stat.py <base> 2024-06 2024-06 1` (one origin, in-process). Then delete `stage2\members\members_2024-06.parquet`.
4. **Baseline (untuned) pass**: s2stat over origins 2022-10..2026-10, s2tree with the starting settings, s2eval, s2live. This is the fallback.
5. **Tuning (protocol section 6a)**: only on 2023-24 targets, never 2025/2026.
   - Tree model: trial 0 = defaults, then 40 random-search trials from a fixed seed.
   - Three-quantile proxy (0.10/0.50/0.90). One model per horizon, with shared settings scored on the mean over horizons.
   - Fixed seeds. Two fixed feature sets. Tweedie power from a 4-value grid.
   - Boosting rounds are fixed after tuning, with no early stopping on 2025/26.
   - SBA/TSB alpha from {0.05, 0.1, 0.2, 0.3} and ADIDA length from {2, 3, 4, 6}, per demand class.
   - Adopt a tuned setting only with a 1%+ gain AND a win in 2023 and in 2024 separately.
   - Time one trial first. If 40 trials would pass 8 hours, cut the count (never below 15). If 15 don't fit, use a fixed-seed random half of the series. Report this.
   - Save every trial's settings and score.
6. **2025 layer test** (section 9: 2% gain AND 90% of 1,000 block-bootstrap resamples), and coverage for each half of 2025. Then **2026 reported once**.
7. **Freeze by Nov 30**: copy to `/freeze/` with a manifest: forecast file, product list, brand/vendor/category maps, cleaning rules, protocol, code version, SHA-256 of each raw file, units files, Addendum 5 outputs. Copy it into the project's `iowa-liquor/freeze/` too.

## Do not
- Push, commit or post anything to GitHub or any site without Dawson's explicit OK.
- Use 2025 or 2026 targets for any choice. Don't rerun the pre-declared target check. Don't read any score before the step that reports it.
- Change dollars (they never change), the raw Parquet files, or the protocol thresholds.
- Install software without Dawson's direct OK. Never handle his passwords.
- Keep printed output short. Write the detail to files.

## Added by the design thread (Nov 27 2026, 8:15 PM PT)
The order of next steps above matches the design thread's order. Four additions:
1. **Report back at four points** by writing a short text or markdown summary (no data files, under 200 lines each) into `<home>\OneDrive\Desktop\Claude_Allowed\iowa-checkpoints\`, named `01-hand-check.md`, `02-timing.md`, `03-tuning.md`, `04-test-2025.md`, and tell Dawson each time one is written. The design thread reads that folder directly, so Dawson does not need to paste anything. If the session cannot write there, give Dawson the summary to paste instead. The four points, going on except where it says stop: (a) the hand check result with the full break list (go on if it passes; stop if it fails); (b) the one-trial timing and the number of tuning trials that will run (go on); (c) the tuning table: every trial, the chosen settings, the gain, and whether the 1% and two-year rule adopted them (go on); (d) the 2025 layer test and coverage by half year (STOP: the design thread and the judge read this before 2026 is run). 2026 is run once, after that OK.
2. **Fallback**: finish and save the baseline pass (step 4) completely before tuning starts. If tuning or the ensemble is not done by Sunday Nov 29 evening PT, the freeze is the baseline plus per-series pool, labelled as such.
3. **Freeze**: the local session builds the package and manifest only. The design thread shows Dawson the file list and makes the public commit after his OK. Copy the package into the project's `iowa-liquor/freeze/` (through Dawson's Claude_Allowed folder if there is no direct path).
4. **Explain as you go**: Dawson wants to see what each block of code does and why. Before each step, say in two or three plain sentences what it does and which protocol section or decision it implements.
