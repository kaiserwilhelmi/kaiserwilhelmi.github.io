# Amendment to ruling-01b (design thread, Nov 27 2026, 9:10 PM PT), from the judge's Addendum 9. Keep building; this changes the end of the step, not the rebuild.

1. **The frozen artifact is `stage1\unit_breaks.csv`, one row per break**: item, month, pack before, pack after, factor, action (`restate`, `cut`, `leave_alone`), evidence, reader. It replaces `unit_breaks_manual.csv`. The rule proposes each row; the hand reading decides the action. The notebook and verify apply the actions from this table.
   - Never restate on an uncertain reading: cut if continuity fails, otherwise leave alone.
   - `leave_alone` is a valid action: 924890, 19029, 42462 as ruled. 84161 is `restate`, factor 1/10.
   - Read the last 4 inactive breaks that the seed-60 sample left out, so every break in the table has been read.
2. **Pass rule, replacing "3 wrong and 2 wrong"**: the gate is that no item with action `restate` in the final table reads wrong or uncertain. Report the rule's raw error rate before the table (it does not gate).
3. **Stop only if** the real rerun produces a break that was not in the dry run. Then read it, add it to the table with its reading, say so in the checkpoint, and continue.
4. **Second reader**: for every restated item above $50,000 trailing-12 dollars (the 99 minis, 38449, 84161 and any other), write `01d-second-reader.md` to `Claude_Allowed\iowa-checkpoints\` with, per item: monthly bottles, dollars, dollars per bottle and recorded pack for the 6 months each side of the break, the count of lines at each price in the break month, and the factor applied. Someone who did not build the rule reads it in the cloud.
5. **Order from here**: write `01d-hand-check.md` and `01d-second-reader.md`, then go on with step 2 (liters tiers and outputs) and step 3 (timing, with the truncation test) without waiting. **Do not start the baseline pass (step 4) until `ruling-01d.md` appears**; it will carry the second reader's result.
6. **28081 Prairie Fire mini**: flag it on its product row and report its score separately.
7. **Live months (for s2live and the manifest)**: a detected break with pack ratio 3 or more that passes continuity is restated for grading; under 3 is read by hand first.

8. **See also `ruling-01b-amend2.md`** in this folder (added 9:15 PM PT): it sets the layout of `01d-second-reader.md` (raw state figures first, the applied factor in a separate final section).
