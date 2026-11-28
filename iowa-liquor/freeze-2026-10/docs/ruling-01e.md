# Ruling on 01e and 02 (design thread, Nov 27 2026, 11:59 PM PT). GO: nothing here stops the baseline or tuning.

## 02-timing: accepted
Table hash, 87035 unsplit, truncation tests (and the tie-break fix they found), the MKL threading workaround, and 40 tuning trials on all series are all accepted. Carry on: baseline, then tuning, then `03-tuning.md`. Two reminders before the freeze: (1) protocol section 2's direct ETS ranges and their calibration for brand, category and state are still to build; (2) list the MKL setting and the overwritten `backup_pre62` in the manifest notes.

## 01e, liters (decision 66; the judge and the second reader are reviewing, expect at most a small amendment)
1. **A unit break alone never proves liters.** The proven tier needs the state's own size history for the item (a larger recorded size before a smooth change to the smaller one). "Proven (unit break)" with no size history is removed as a tier reason.
2. **For every restated series (all 21, not only the 15 above $50,000)**: proven only if it has size history AND the rule's liters per current unit equal the price-implied figure within rounding. Otherwise unknown, left out of liters.
3. So, of the 15: **proven** = 81124, 84197, 84207 (6.0 L per current unit). **Unknown** = 84226, 84172 (7.2 L against 6.0 L), 101180, 84222, 84155, 84242, 38449 (no reference price), 84224, 84161, 76359, 84104, 84400. Apply the same test to the other 6 restated series and report each one's tier in `03-tuning.md`.
4. The `held` tier ends once this is applied: every series is proven, standard or unknown. Rerun units_tiers, the liters check in verify, and the brand coverage shares; a brand above 5% unknown is labelled partial (99 Brand will be).
5. Units and dollars for these items are unaffected and final.

## 01e, the rest: accepted, no action
Tito's 38449 Nov 2025 is one price ($15.75) with the state's whole-dollar line totals; factor 8 stands. 84161 is cut for the reason given. The May to Oct table goes to the second reader and the judge; fitting is unchanged in version 1 unless a ruling file says otherwise.
