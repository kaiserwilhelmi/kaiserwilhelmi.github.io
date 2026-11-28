# Ruling on checkpoint 01b (design thread, Nov 27 2026, 9:05 PM PT). GO: rebuild and continue.

Good work stopping, and the dry run was the right way to test it. Rulings (decision 62; protocol is now v1.10, refreshed in this folder with decision-log.md; copy both into `C:\ds\iowa-liquor\docs\`). The judge is reviewing these in parallel; if anything changes, a file `ruling-01b-amend.md` will appear here, so look for it when you write your next checkpoint.

1. **Mixed months: adopt your variant.** Inside a break's windows, assign each line to the old or new unit by its own price (nearer in log to the before or after median), then by recorded pack, then by month. Detection, both bands, chained confirmed factors and the continuity test stay as they are.
2. **Calendar cap: adopt.** Before and after medians use up to 3 months with orders that lie within 12 calendar months of the break. If no month qualifies on a side, the pack change is not a break (left alone, listed).
3. **Continuity test: unchanged** (units 0.5 to 2 AND dollars per restated unit 0.67 to 1.5; a failing item is not restated and its series starts at its last break). It is the judge's rule and cutting cannot put a wrong number in. So 76270 is cut at Apr 2026 instead of restated by 6; that replaces the earlier known answer. 66537, 69608, 986990, 12865, 101575 and 989062 are cut the same way.
4. **Manual table `unit_breaks_manual.csv`, fixed now, before any score** (columns: item, month, action, factor, evidence):
   - 84161 99 Blackberries, Oct 2024, restate, factor 1/10, evidence as you wrote it. If the 12-month cap makes the rule confirm it anyway, leave the entry out and say so.
   - 924890 Obtainium, 19029 Jim Beam Black 375, and 42462 Brugal 1888 (only if the rule still confirms it after the cap): action `leave_alone`, meaning neither restated nor cut, evidence = your reading (case size plus price change).
   - Nothing else goes in the table without a new ruling.
5. **Flag, do not change**: 87035 Skrewball mini (price toggles), 65933 Malibu Pink mini (number reused for a 1.75 L), 28081 Prairie Fire mini, and the 2012 unit flips on 84172 and 84160. Put each one's trailing-12 dollars in the checkpoint. I will rule on a split for 65933 or 87035 only if either is above $50,000.
6. **Decision 61**: flag the 4,942 lines with bottles and $0 and the 8 lines with dollars and 0 bottles; bottles kept, dollars unchanged, both left out of price medians.
7. **01c accepted.** The Nov 2025 to Jan 2026 whole-number prices are a disclosure item, nothing to change. Blank-category lines taking the item's most common category is fine; confirm it in the stage 2 code.

## What to do now
a. Build 1 to 6 in `build_nb.py` and, independently, in `verify_stage1.py`. Rerun the notebook, verify (every line OK), the link diff (confirm 12856 links to 12860 again) and brand_map / addendum5 / make_hand_extra.
b. Redo both hand reads on the REAL outputs and write `01d-hand-check.md` to `Claude_Allowed\iowa-checkpoints\`: the main check on every break on items with trailing-12 sales (count a break wrong when the rule's own detection is wrong, before the manual table; also show the final outcome per item), and the same seed-60 sample of 20 for the second read.
c. **Pass = main check 3 wrong or fewer AND second read 2 wrong or fewer.** If both pass, do not wait: go straight on to step 2 of HANDOFF.md (liters tiers and outputs), then timing with the truncation test, baseline, tuning. If either fails, stop and wait for `ruling-01d.md`.
d. Finish part 2 of 01c after the rebuild; it does not block anything.
