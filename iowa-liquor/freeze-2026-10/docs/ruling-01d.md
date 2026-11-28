# Ruling on checkpoint 01d (design thread, Nov 27 2026, 10:25 PM PT). GO: the baseline pass is released after the table update below.

The second reader (the data and SQL reviewer, who did not build the rule) read Part A before Part B: **14 of 15 agree on the factor and on "one unit change, not a price change", 0 disagree, 1 cannot tell (84161, which ends up cut, so nothing is restated on an uncertain reading).** The judge agreed decision 63 in Addendum 10. Refreshed `decision-log.md` is in this folder; copy it to `C:\ds\iowa-liquor\docs\`. If the judge amends anything, `ruling-01d-amend.md` will appear here.

## A. Update the frozen table `stage1\unit_breaks.csv`, then rerun the notebook and verify (every line OK)
1. Two columns: `proposed_action` (what the reading proposed) and `action` (the final outcome). 84161 is proposed `restate`, final `cut`.
2. Add rows: 84160, `cut` at 2021-03; 69608, `cut` at 2026-08 (both as you proposed).
3. Add a `cut` row at the 2012 unit flip for 84172 (Jul-Aug 2012), so its factor of 12 is not applied to early-2012 lines that are in a third unit. 84160 is already cut later, so it needs no 2012 row.
4. 87035 Skrewball mini: test whether the lines at about $21.00 and the lines at about $4.95 carry different recorded sizes (`bottle_volume_ml`) or packs. If the recorded size differs, split the item on recorded size into two products and say so. If not, leave it unsplit, flagged.
5. No other row changes. If the rerun changes any break outcome other than these, stop and write `01e`.

## B. Stage 2 rules confirmed
6. "Scored separately" for 87035 (if unsplit) and 28081 means: left out of the selection metric and out of the headline test score, with their own scores shown beside it and their share of dollars.
7. Restated units are fractions before a break. Confirm in `02-timing.md` that nothing downstream assumes whole counts (count-based quantiles are computed in the recorded unit and then converted, as the protocol says; zero tests use > 0, not == an integer).
8. The May 2023 change on the 99 minis is followed by a real step up in orders (stores that ordered about six sleeves a line had to order a case of ten). No correction is made and no model input is added for it in version 1. Mark the break month and the month after as `unit_change_window` in the outputs, and name these items beside the 2023-24 tuning scores.
9. The old decision 48 carrier list in `brand_map.py` must be gone before the freeze. If the file is still locked, write the corrected file under a new name, point the imports at it, and note it in the manifest.

## C. Follow-up for the second reader: write `01e-second-reader-followup.md` to `Claude_Allowed\iowa-checkpoints\` (does not block the baseline)
10. 84161: all its months before 2024-10 with raw bottles, dollars, price and pack, and why it is cut and not restated.
11. For the same 15 items: raw monthly figures for May to Oct 2022 (the same season a year before the change).
12. Tito's 38449, Nov 2025: what the 24 lines at $15.00 and the 5 lines at $15.50 and $15.67 are.
13. **Liters per current unit for each of the 15 items**: recorded ml, the item's size history (every recorded ml value with its first and last month), the decision 51 tier it lands in, the liters per current unit the code uses, and the evidence. The reader's inference from prices is 120 minis (6 L) per current unit for the 99 minis. Liters for these items are not final until this is read; unit counts are.

## D. Order
A (table, rerun, verify), then **step 4, the baseline pass**, with timing and the truncation test reported in `02-timing.md` first. C can be written while the baseline runs. Then tuning per section 6a. Stops are unchanged: a failed check, or `04-test-2025.md`.
