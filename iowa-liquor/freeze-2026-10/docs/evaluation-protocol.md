# Evaluation protocol: Iowa liquor demand forecast

Version 1.10, written Nov 27 2026 (Pacific) by the design thread, BEFORE any model has been scored on real data (see the note on earlier runs below). Implements judge rulings B4 to B8 and the judge's Addenda 1 and 2 (review/judge-verdict.md). Versions 1.0 to 1.9 are kept as evaluation-protocol-v1.0.md to -v1.9.md. Any later change is a new dated version with the reason, and is reported on the page.

Changes from 1.0: calibration now runs in time order (P1); coverage bands are dollar-weighted with floors only for slow items (P2); "new" and "intermittent" split (P3); added rules M1 to M6; bootstrap stated as overlapping and paired.

Changes from 1.1 (Addendum 2): price and dollar wording tied to decisions 32 and 33; a pre-declared check on whether to model per order day; longer calibration windows where there are too few errors; one named calibration retry; a rule for series with no scale in the tree model; order days follow decision 36.

Changes from 1.2 (stage 1 evidence from real data, decisions 42 and 43): the forecast unit is a linked product series, because 4.7% of recent bottles sit on renumbered items; effective order days are the rule, because the weekday calendar failed validation (57.9% of months within one day against a 95% bar).

Changes from 1.3 (judge's Addendum 3): open handover windows are fenced out of the selection metric; links may bridge a gap as well as an overlap and must be one to one; live grading is on units as frozen; order-day shares for the first 24 months and for training rows are defined.

Changes from 1.4 (decisions 46 and 50 to 53, judge's Addenda 4 to 6): links need a price guard; the state changed what one "bottle" is for some products, so unit breaks are restated into the current unit; liters come in evidence tiers and are a secondary measure; units appear on product pages only. What had run before this version: the pre-declared target check (seasonal naive per order day against raw monthly bottles, 2023 to 2024), on linked but unrestated data. It stands and is not rerun; the page says it ran on unrestated data. One single-origin timing run of the stage 2 code, with no scores read. No model had been scored.

Changes from 1.5 (decision 55, Dawson's request of Nov 27 that the models be tuned): section 6a sets out a fixed tuning plan on 2023 to 2024 targets only. Nothing about 2025 or 2026 changes. Written before any model was scored.

Changes from 1.6 (judge's Addendum 7): boosting rounds fixed after tuning; a two-year condition added to the stop rule; each member tuned on its own score; the tree model is one model per horizon; a fallback if 15 trials do not fit the cost cap; 2025 coverage reported by half year.

Changes from 1.7 (decision 60): the unit-break rule of version 1.5 failed its hand check (18 of 37 wrong), so it is replaced by a rule that takes the factor from the state's own pack field. Still no model scored.

Changes from 1.8 (judge's Addendum 8): only confirmed breaks are chained into a line's factor; the pack ratio is used by rule only when price agrees within 0.8 to 1.25; a continuity test per restated item; a small manual table for hand-read cases; a truncation test before any score is read.

Changes from 1.9 (decision 62, after a dry run on real data): the state changes the pack field on all of an item's lines before the unit itself changes, so lines near a break are assigned by their own price, not their recorded pack; price medians come from within 12 calendar months of the break; a short manual table of leave-alone entries is allowed for items with recent sales.

## 1. What is forecast
- Series: product by calendar month, statewide. A product is a series_id: item numbers that share a description and bottle size and hand over from one to the next are one series (decision 42). Links are made only when the older number's last order falls from 90 days before to 90 days after the newer number's first order, and only when the match is one to one; other cases are listed and decided by hand in the top chains only. Target: bottles per statewide effective order day. Monthly bottles = forecast x effective order days in that month.
- Order days: effective order days (decisions 36 and 43). For a month, sum over the seven days of the week of (count of that day in the month, state holidays removed) x (that day's share of statewide bottles over the 24 months before the origin, scaled so a full week sums to 5). Shares are known at the origin and the counts come from the calendar. Origins in the first 24 months of data use the earliest 24 months' shares. Each training row takes the shares as of its own origin. A listed holiday that regularly carries orders is dropped from the holiday list. Never counted per item.
- Price guard on links (decision 46): a link is made only when the older number's median dollars per bottle over its last 12 months with orders is 0.67x to 1.5x the newer number's median over its first 12 months with orders. The band is fixed.
- Unit breaks (decision 60, replacing decision 50's detection): the state sometimes changes what one "bottle" is for an item (a sleeve of minis becomes a case of sleeves) and changes the item's recorded pack at the same time. A unit break is a change in the item's recorded pack from one value to another where (i) old pack / new pack is 1.8 or more, or its inverse is, and (ii) dollars per bottle moved the opposite way by about the same amount: (median price after / median price before) divided by (old pack / new pack) is within 0.67 to 1.5. Medians are over order lines in up to 3 months with orders on each side, all within 12 calendar months of the break; one month is enough. A pack change where the price per bottle did not move this way is a real change of case size and is left alone. A price step with no matching pack change is a price change and is left alone.
- A break is confirmed by rule only when price ratio over pack ratio is within 0.8 to 1.25. Between that and 0.67 to 1.5 it is read by hand and gets no automatic factor. Hand-read cases go in a short manual table, each entry needing units and price to move by the same whole number, with the evidence beside it, fixed before any score; anything else is left alone and flagged.
- Restatement is done line by line: a line's factor is the product of the confirmed break ratios (new pack / old pack) between the line's date and now. Inside a break's windows each line is assigned to the old or new unit by its own price (nearer, in log terms, to the before or the after median), then by recorded pack, then by month, because the state changes the pack field on every line of the item before the unit itself changes. An unconfirmed pack change (an ordinary change of case size) contributes 1. The factor is the pack ratio itself, never a rounded price ratio.
- Continuity test on every restated item: restated units after / before the break within 0.5 to 2, and dollars per restated unit within 0.67 to 1.5. An item that fails is not restated and its series starts at its last break. For items with trailing-12 sales, the manual table may also mark a detected break as an ordinary case-size or price change after a hand read: that item is neither restated nor cut. Every manual entry carries its evidence and is fixed before any score. Histories are never cut. Dollars never change. Price = dollars over restated units. Count-based quantiles (negative binomial) are computed in the recorded unit and then converted. Every detected break is read by hand and recorded in one table, unit_breaks.csv, with an action (restate, cut, leave alone), the evidence and the reader. The rule proposes, the reading decides, and the table is fixed before any score. Nothing is restated on an uncertain reading. Every restated item above $50,000 of trailing-12 sales has a second reader who did not build the rule. Gate: no restated item in the final table reads wrong or uncertain. The rule's raw error rate before the table is reported (version 1.10, judge's Addendum 9; this replaces the counts of 3 and 2). In live months a detected break with pack ratio 3 or more that passes continuity is restated for grading; under 3 is read by hand first. If it fails again, restatement is dropped and each affected series starts at its last break, labelled as such. Price steps of 1.8x or more with dollars smooth and no pack evidence are listed, not restated; those above $50,000 of trailing-12 sales are read by hand and reported. Breaks inside 2025 to 2026 are reported beside the test score. A break of the same kind after a freeze is restated into the frozen unit for grading and shown beside the grade.
- Pre-declared check, run once on 2023 to 2024 before any other model: if seasonal naive per order day does not beat seasonal naive on raw monthly bottles on the selection metric, the target becomes raw monthly bottles for every model and order days are kept as an input only.
- Outputs per series, origin and horizon: a mean forecast and seven quantiles: 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95. Quantiles are sorted after prediction. Nothing is negative.
- The ensemble mean is the equal-weight average of the pool members' means. Each ensemble quantile is the equal-weight average of the members' quantiles at that level.
- Horizons: 1, 2 and 3 months ahead. Every score is reported by horizon.
- Liters and 9-liter cases are a secondary measure, in three tiers per item and period (decision 51). Proven: the state's own size history gives the pack factor (larger over smaller recorded size, on rows at the smaller size, chained with any unit break); the corrected dollars per liter must sit within 0.5x to 3x the brand median or the item is read by hand. Standard: liters = units x recorded size. Unknown: dollars per liter 4x or more the brand median with no size history, and either a recorded size of 200 ml or less or a description that marks a pack; no factor is guessed and these series are left out of liters. Full-size series over 4x stay standard, with the largest read by hand. Dollars = forecast bottles x the average price stores paid per bottle (sales dollars / bottles, item median over the last 3 months with orders, as of the origin).

## 2. Higher levels (brand, category, state)
- The number that adds up: the bottom-up sum of product means. This is the headline figure at every level.
- Ranges: each brand, category and state series is also forecast directly with seasonal exponential smoothing (section 6 settings), calibrated in time order per level (section 8). Ranges are not forced to add up, and the page says so.
- If the bottom-up sum falls outside the level's own direct 50% range, both are shown and the row is flagged.
- Named brand totals appear only where at least 95% of the brand's trailing-12 dollars sit on hand-checked series, with the share shown; otherwise the total is labelled "hand-checked products only" (decision 49).
- Measures by level (decision 52): product pages show units with the unit named. Brand, category and state show dollars first and covered liters second, with the share of dollars the liters cover; above 5% unknown the liters are labelled partial. Units are not summed above the product, because a mini pack and a 1.75 L bottle would each count as one.

## 3. Which series are scored
- Active at an origin: at least one order in the trailing 12 months as of the origin. Same rule at every origin.
- New series (first order after the origin, and not a continuation of an existing series) are not scored; their count and dollar share are reported.
- Open handover windows: a series and origin where the newer number has started and the older number's last order is after the origin. These series-origins are left out of the selection metric; their count and dollar share are reported per origin; the 2026 test is reported with and without them.
- Discontinued products stay in the scored set (their zeros count).
- Series whose scale (section 4) is zero or undefined are left out of the selection metric; their count and dollar share are reported.

## 4. The one selection metric
Scaled, dollar-weighted pinball loss, defined here in full:
- Pinball loss for quantile level q, forecast f, actual y: (y - f) x q if y >= f, else (f - y) x (1 - q).
- Per series, origin and horizon: average the pinball loss over the seven quantiles.
- Scale per series and origin: mean absolute month-to-month change of the target over the training window available at that origin (from the item's first order month). It is the same for every model.
- Scaled loss = averaged pinball loss / scale.
- Weight per series and origin: the item's share of dollars (as defined in decision 32) in the 12 months before the origin, among scored series.
- Metric = weighted sum over series, averaged over origins, reported per horizon and as the mean of the three horizons. Lower is better. The mean over horizons 1 to 3 is the number used for choices.
- Choices are driven by the PRODUCT-level metric only. The same metric and coverage at brand level are reported beside it on the page, and never used to choose.
- Mean forecasts are reported with a scaled, dollar-weighted squared-error measure, for information only.

## 5. Coverage is a check, not a selection metric
- Reported by horizon and demand class: share of actuals inside the 50% range (0.25 to 0.75) and the 90% range (0.05 to 0.95), plus, separately, the share above the 0.95 quantile and the share below the 0.05 quantile.
- Pass rule on the judging year, applied to DOLLAR-WEIGHTED pooled coverage and to the regular classes: 90% range between 85% and 95%; 50% range between 44% and 56%.
- For intermittent and lumpy classes only the floors apply (at least 85% and at least 44%), because ranges that start at zero over-cover with whole-number data.
- A fail allows one named retry: the calibration window widens from 12 to 24 months. If that also fails, the uncalibrated ensemble is published with its measured coverage stated. A fail never picks a model. Coverage is claimed on average, never per product.

## 6. Models, pools and settings (fixed before any run)
Demand class at an origin, on the monthly series over the 24 months before the origin:
- New: under 12 months since first order. Pool = global tree model + the item's own mean per order day (quantiles for the own-mean member as for the intermittent methods below).
- Intermittent or lumpy: by the Syntetos-Boylan-Croston convention (average interval above 1.32; squared CV 0.49 splits intermittent from lumpy), or 12+ months of history with under 2 non-zero months in the window. Pool = SBA + TSB + ADIDA + global tree model.
- Regular (smooth or erratic): Pool = seasonal exponential smoothing + global tree model.
- Original Croston is not used.

Settings:
- Seasonal naive (baseline): same month last year, per order day; for items with under 13 months, the mean of available months. Quantiles = point forecast plus the empirical quantiles of the series' own seasonal-naive errors over the last 36 months available at the origin, floored at zero.
- Seasonal exponential smoothing: additive-error ETS on bottles per order day, chosen by AICc among level only, level + season, damped trend, damped trend + season; seasonal forms only with 36 or more months of history. Quantiles from the model's analytic forecast variance (normal), floored at zero.
- SBA and TSB: smoothing parameters tuned per demand class under section 6a (0.1 is the starting value and the fallback).
- ADIDA: non-overlapping totals ending at the origin (3 months unless section 6a picks another length), simple exponential smoothing with the parameter fitted on training data (bounds 0.05 to 0.5), split equally back to months.
- Quantiles for SBA, TSB, ADIDA and the own-mean member: negative binomial on MONTHLY BOTTLES (mean = rate x order days), dispersion by method of moments from the series' last 24 months at the origin; Poisson when variance does not exceed the mean; when the series has under 6 non-zero months, the median dispersion of the estimable series in the same class at that origin. Converted back to bottles per order day.
- Global tree model: one LightGBM across all products on scaled series (each series divided by its section 4 scale), one fit per quantile plus a Tweedie fit for the mean; inputs are only values known at the origin (lags, rolling statistics, month, effective order days, category, vendor as of origin, class as of origin, months since first order, average price stores paid per bottle as of the origin). The scale is taken as of each yearly fit. Series whose scale is zero or undefined are left out of the tree model's training rows and get their forecast from the statistical members of their pool only. Hyperparameters chosen on 2023 to 2024 only, by the plan in section 6a.

## 6a. Tuning plan (fixed before any model is scored)
All tuning uses rolling monthly origins with targets in 2023 and 2024, horizons 1 to 3, and the section 4 selection metric. The 2025 and 2026 targets are never used to tune. The yearly-fit rule of section 7 applies inside tuning (a fit on data through 2022 forecasts 2023 targets; a fit through 2023 forecasts 2024 targets).
- Global tree model: random search, 40 trials from a fixed seed, plus the default settings as trial 0. Ranges: num_leaves 15 to 255 (log scale), min_data_in_leaf 20 to 500 (log), learning_rate 0.02 to 0.1 (log), feature_fraction 0.5 to 1.0, bagging_fraction 0.5 to 1.0 with bagging every round, lambda_l2 0 to 10. Boosting rounds: up to 2,000, chosen by the score on 2023 targets in the first fit and reused in the second. To keep the cost reasonable each trial fits three quantiles (0.10, 0.50, 0.90) and is scored on the mean pinball loss of those three; the winning settings are then used for all seven quantiles. The Tweedie mean model takes the same tree settings, with its variance power chosen from 1.1, 1.3, 1.5, 1.7 on scaled squared error of the mean.
- Feature sets: two candidates only, fixed here. Base (lags 1 to 13, rolling means and standard deviations over 3, 6 and 12 months, and the section 6 inputs) and base plus same-month values from one and two years back with category-level rolling means. The better one under the default settings goes into the search.
- SBA and TSB: each smoothing parameter from 0.05, 0.1, 0.2, 0.3, chosen per demand class, not per series.
- ADIDA: aggregation length from 2, 3, 4, 6 months, chosen per demand class.
- Exponential smoothing: no extra tuning. Its parameters are already estimated per series and the form chosen by AICc.
- Tree model structure: one model per horizon (1, 2 and 3 months ahead), each using only inputs known at the origin. One set of tree settings is shared by the three horizons and is scored on their mean. Random seeds of the model are fixed.
- Each member is tuned on its own score: the three-quantile proxy for the tree model, the full selection metric within class for SBA, TSB and ADIDA.
- Boosting rounds are fixed after tuning and reused for the fits that forecast 2025, 2026 and live months. No fit is ever stopped early against 2025 or 2026 targets.
- Stop rule against over-tuning: tuned settings replace the starting values only if they lower the member's score on 2023 to 2024 by 1% or more AND beat the starting values in 2023 and in 2024 separately; otherwise the starting values stay. Starting values for the tree model: num_leaves 63, min_data_in_leaf 100, learning_rate 0.05, feature_fraction 0.8, bagging_fraction 0.8, lambda_l2 1.
- Cost cap: if one trial takes so long that 40 would pass 8 hours on Dawson's PC, the number of trials is cut to what fits in 8 hours (never below 15), same seed and order, and the number run is reported. If 15 trials do not fit in 8 hours, tuning runs on a fixed-seed random half of the series and the page says so.
- Truncation test before any score is read: delete all data after one origin, rerun, and the forecasts for that origin must be identical.
- Reported: every trial's settings and score, the chosen settings, and the gain over the starting values. Scores on 2023 to 2024 are flattered by tuning and are labelled so; 2025 judges layers (section 9) and 2026 is reported once.
- Effect on the 2025 checks: early 2025 calibration windows hold 2024 errors that tuning made a little small, so ranges may come out a little narrow. Coverage is reported for the first and second half of 2025 separately; a miss in the first half only is reported, not fixed.
- Still later challengers, not tuned now: learned ensemble weights, per-series intermittent parameters, MinT.

## 7. Roles of the years
- Training: Jan 2012 to Dec 2022 for the first fit; the window then expands with each origin.
- Choices (hyperparameters, any design choice not fixed above): rolling monthly origins with targets in 2023 and 2024.
- Judging any learned or more complex layer: targets in 2025 only.
- 2026: reports only. Run once, after everything above is fixed. January to October, or January to September if October 2026 is ruled incomplete (decision 30, ruled before this run).
- Backtests mirror production: the global tree model is fitted once per year (data through December) and fed new months without refitting; per-series models are refitted at each origin.
- The live forecast is the chosen specification refit on data through the last complete month, settings unchanged, labelled as a refit of the tested procedure.
- 2020 and 2021 stay in training, unflagged, for version 1.

## 8. Calibration (in time order)
- Split conformal adjustment of each quantile, pooled across products within demand class, per horizon, on scaled errors.
- For each origin and horizon, the calibration set is the scaled errors of the uncalibrated ensemble on the 12 most recent target months already observed at that origin. The live forecast uses the same rule.
- So 2025 is out of sample for the coverage check and for the layer (c) versus (d) comparison. Stated limit: for 2025 targets some calibration errors come from 2023 to 2024, the years used for choices, so they are slightly flattering.
- Higher levels are calibrated the same way, pooled within level. A calibration set needs at least 19 errors per horizon: the state level uses a 36-month window, and the category level does too if it has fewer than 19.

## 9. The layer rule
- Ladder for version 1: (a) seasonal naive; (b) per-series statistical pool; (c) equal-weight average of the statistical pool and the global tree model; (d) the same with conformal calibration.
- A more complex layer replaces the simpler one only if it lowers the product-level selection metric on 2025 by 2% or more AND the gain is positive in at least 90% of 1,000 moving-block bootstrap resamples over months (overlapping blocks of 3 months; both models resampled on the same months). With 12 months this test has low power, so complex layers will often fail it. That is the intended safe direction.
- Learned ensemble weights, MinT reconciliation, a direct dollar model, per-series SBA/TSB parameters and horizons 4 to 6 are later challengers under this same rule.

## 10. The live scorecard
- The frozen package (forecast file, product list, item-to-brand, vendor and category maps, cleaning rules, this protocol, code version, SHA-256 of each raw file) is fixed before the state posts the month being forecast.
- Each month gets a provisional grade on the first file that contains it and a final grade on that month as it stands in the next monthly file; the final grade is then fixed. Every file is kept and hashed; later revisions are shown beside the grade.
- Live grading is on units as frozen. A number first seen after the freeze that continues a frozen series counts toward that series' actual. Two series frozen separately and linked later stay separate for that vintage. A link confirmed after a final grade is shown beside it.
- Label for the first frozen month: "one month ahead, from data through [last complete month], frozen on [date]; November's orders had happened but were not published".
- Fallback: if layers (c) and (d) have not passed this protocol by the freeze date, layers (a) and (b) are frozen and labelled as such, and the ensemble joins next month as a new version.

## 11. Judgment calls in this protocol (not findings from the literature)
The 2% margin and 90% bootstrap rule, 3-month blocks, horizons 1 to 3, the coverage bands and floors, the 12-month active rule, the 24-month class window, the 12-month "new" rule, fixed smoothing values of 0.1, the 3-month ADIDA level, the 36-month error window for seasonal naive, the dispersion fallback, the 12-month calibration window, the scale definition, and the grading rule in section 10.

## Sources
- Makridakis et al. (2022), M5 uncertainty competition, IJF 38(4), 1365-1385 (record verified by the judge; the exact metric definition was not, which is why section 4 defines its own).
- Syntetos, Boylan and Croston (2005), JORS 56(5), 495-503 (record and abstract verified by the judge).
- Gneiting, Balabdaoui and Raftery (2007); White (2000); Hansen, Lunde and Nason (2011); Tashman (2000); Barber et al. (2023); Gibbs and Candes (2021); Kolassa (2016) (as cited by the reviewers or judge; not re-opened by the design thread).
- Snyder, Ord and Beaumont (2012), IJF 28(2), 485-496; Syntetos and Boylan (2005); Teunter, Syntetos and Babai (2011); Nikolopoulos et al. (2011); Kourentzes (2014) on parameter choice (from memory, to be checked before use on the site).
