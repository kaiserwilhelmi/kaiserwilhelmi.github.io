# Forecast Method Comparison

**Business question:** Which forecasting method should a buyer trust for a given demand or price series, and how wrong is it likely to be?

The page backtests up to fourteen methods (statistical and machine learning) on a series with a rolling origin, scores them on seven error measures, and lets the data pick the winner. No method is favoured in advance. It also checks whether the winner holds up when the backtest window changes (12, 24, 36 periods). Pick any of the 100 Industry Market Watch series (grouped, with search) or upload your own CSV or Excel file. Everything runs in the browser; uploaded files never leave it.

## Methods
| Method | Reference |
|---|---|
| Naive, Seasonal naive, Drift | Hyndman & Athanasopoulos (2021) §5.2 |
| 3-month moving average | FPP3 §3.3 |
| Simple exponential smoothing | FPP3 §8.1 |
| Holt linear trend | Holt (2004 [1957]); FPP3 §8.2 |
| Damped trend | Gardner & McKenzie (1985); FPP3 §8.2 |
| Holt-Winters additive (weights + starting states fitted) | Winters (1960); FPP3 §8.3 |
| Seasonal ARIMA(0,1,1)(0,1,1)m, the "airline model" | Box & Jenkins (1970); FPP3 §9.9 |
| Regression: linear trend + seasonal dummies | FPP3 §7.4 |
| Theta method (SES + half the trend; seasonal adjustment when a 90% ACF test finds seasonality) | Assimakopoulos & Nikolopoulos (2000); Hyndman & Billah (2003) |
| ML: ridge regression on the last p scaled changes (λ chosen on a holdout), recursive forecasts | Hoerl & Kennard (1970) |
| ML: gradient-boosted trees (150 depth-2 trees, learning rate 0.05) on the same features | Friedman (2001) |
| Combination: average of Holt-Winters + seasonal ARIMA (seasonal data) | Bates & Granger (1969); Makridakis et al. (2020) |
| Combination: average of SES + Holt + damped (no seasonality; the M4 "Comb" benchmark) | Makridakis et al. (2020) |

**Fitting.**
- Holt-Winters: α, β, γ and the starting level, trend and m seasonal terms are fitted together by minimising one-step squared error with a Nelder–Mead search (Nelder & Mead, 1965). This is the least-squares version of the ETS(A,A,A) fit in FPP3.
- Seasonal ARIMA: θ and Θ fitted by conditional sum of squares (Nelder–Mead).
- SES / Holt / damped: weights from a grid (α, β ∈ {0.05, …, 0.95}; φ ∈ {0.80, …, 0.98}). Full optimisation changed their accuracy by under 1% on these series, so the simpler, faster fit was kept.

**Why these choices (tested before building).** On the five series (24-month window, 6 steps ahead), fitting Holt-Winters' starting states lowered its average MASE from 0.581 to 0.498, and seasonal ARIMA was the best method on both real seasonal series. Accuracy matches the statsmodels maximum-likelihood fits closely (Cass freight: Holt-Winters 0.408 here vs 0.404; seasonal ARIMA 0.393 vs 0.404). A nested test (choose the method on an older 24-month window, score it on the newest 12 months) beat the naive forecast on every series, which supports letting the backtest choose.

## Machine learning: tested before adding
`research-ml/` benchmarks every method on 80 real FRED series (Market Watch) plus 6 series with other time units (rolling origin, 6 steps ahead). Theta, ridge and seasonal ARIMA had the lowest median MASE (0.31). Picking the method on an older window and scoring it on the newest 12 months, the extra methods cut mean MASE on the real series only from 0.490 to 0.486 (Wilcoxon p = 0.42, better on 9, worse on 15). A 5-network MLP ranked worst and was ~6x slower, so it was left out. This matches Makridakis, Spiliotis & Assimakopoulos (2018) for short single series; ML won M5 with thousands of related series and covariates (Makridakis et al., 2022). The ML methods stay as candidates because they win on some series (e.g. ridge on exponential growth).

## Evaluation
- **Rolling origin** (Tashman, 2000; FPP3 §5.10): for each of the last N periods (12/24/36), every method is re-fitted on data before that point and forecasts 1..h steps ahead (h = 1/3/6/12). Forecasts that fall inside the data are scored, pooled across horizons. MAE by horizon is also shown.
- **Metrics:** MAE, MSE, RMSE, MAPE, sMAPE, MASE, Bias (mean error = actual − forecast). MAPE is reported as n/a if any actual is zero.
- **MASE scale** (Hyndman & Koehler, 2006): in-sample MAE of the seasonal-naive forecast (naive if seasonality = none) on the training data before the first origin. Note that multi-step errors are compared with a one-step scale, so MASE > 1 is normal at longer horizons. If that scale is zero (a flat history, such as a fixed contract quantity), MASE is undefined, so the page falls back to the naive MAE and then to the average level, and says so; rankings within a series do not change. Values filled into gaps are never scored.
- **Significance:** Diebold–Mariano test (Diebold & Mariano, 1995) with the Harvey–Leybourne–Newbold (1997) correction on per-origin mean absolute scaled errors, against naive (table column) and the runner-up. If the gap could be luck, the page names the simplest method that is not significantly worse.
- **Winner:** lowest MASE (RMSE breaks ties). The recommendation flags near-ties, small gains over naive (< 5%), disagreement between metrics, bias, and whether the winner is stable across 12/24/36-period windows.
- **Speed:** every method is fitted once per origin (longest window, 12 steps ahead); each horizon/window setting is then scored from those forecasts. A k-step forecast doesn't depend on how many steps were requested, so this is exact.

## Uploading your own data
Upload a CSV/TSV/text export or an Excel workbook (.xlsx). Everything is read in the browser (`upload.js`, no libraries; .xlsx is unzipped with the browser's built-in decompression).
- **Layout:** any number of columns and header rows. The value column is the one with the most numbers (you can switch if there are several); the date column is the one with the most readable dates. With no dates, rows are periods 1, 2, 3…
- **File quirks handled:** Excel BOM and UTF-16 "Unicode text", comma/semicolon/tab separators, Mac/Windows line endings, quoted cells, thousands separators, currency and % signs, (negatives), blank or text rows, newest-first order, duplicates, an .xlsx saved with a .csv name, data on a later sheet, and workbooks using Excel's 1904 date system. Old binary .xls gets a message to re-save as .xlsx or CSV; formulas whose results were never saved get a message to re-save in Excel.
- **Decimal mark:** judged from the number cells only (dates such as 01.02.2020 are ignored), so `1.234,5` and `1234,500` in a semicolon file read as 1234.5. When a file could go either way the page offers a Decimal mark toggle. A comma file with an unquoted number such as `1,210.5` (split into two cells) is joined back and flagged; one column of `10,5`-style numbers is read as decimals.
- **Gaps:** missing periods, blank values and NA cells inside a dated series are filled by a straight line between neighbours (the Market Watch rule) and listed on the page, so seasonal lags stay aligned. Filled values help fit the methods but are never scored. More than 10% missing is reported instead of filled. Dates that do not exist (30 February) are dropped with a warning, and two-digit years follow Excel (00–29 → 2000s, 30–99 → 1900s).
- **Dates:** ISO (2020-01-22), US and European numeric (1/22/2020, 22.01.2020), month names (22-Jan, Jan 22 2020, January 2020, Jan-22), quarters (2020Q1, Q1 2020), ISO weeks (2020-W05), years, times (1/22/2020 1:30 PM) and Excel date cells. When dates could be month/day or day/month, the page picks the reading that gives evenly spaced dates, says so, and offers a toggle.
- **Time unit:** detected from the spacing (seconds, minutes, hours, days, business days, weeks, months, quarters, years, or plain periods). Seasonality defaults to 60/60/24/7/5/52/12/4/none respectively (or none if there isn't enough history for two full cycles) and can be changed, including a custom length. Labels, horizon and backtest wording follow the unit.
- `test/uploads/` holds 31 test files (Excel-style CSVs, UTF-16, .xlsx, multi-sheet, quarterly, weekly, hourly, business-day, ambiguous dates, plus one file for each upload bug fixed in the Nov 2026 audit). `node test/test_uploads.js` loads each into the page in headless Chromium and checks count, first and last date, values, time unit, filled periods and messages against `test/expected_uploads.json`, and that the page renders with a finite MASE; it exits 1 on any mismatch. `node test/test_engine.js` checks engine edge cases (flat histories, non-numbers, filled values not scored, NaN-safe ranking, MASE unchanged by units).

## Verification
`verify.py` is an independent Python re-implementation (regression via numpy least squares, a different solver from the JS). `node dump_js.js` runs `engine.js` over 5 series × 2 seasonality settings × 3 windows × 4 horizons (120 cases) plus daily, business-day, hourly, weekly and quarterly test series; `python3 verify.py` compares every metric, MAE-by-horizon value, 12-step future forecast, fitted parameter and the winner at each window: **84,190 values (including Theta, ridge, boosted trees and every Diebold–Mariano p-value, checked against scipy), worst relative difference 9.0e-10, all winners identical.** The Python check uses plain left-to-right sums because Python 3.12+ `sum()` is compensated and would make the optimiser drift from JavaScript's.

## Data
- **Industry Market Watch series (100).** The Series menu lists every series the [Market Watch](https://dawsonwilhelmi.com/market-watch/) tracks, grouped by type and searchable by name, ID, publisher or industry. Only the catalog is built into the page; the numbers are fetched from the Market Watch site (`/market-watch/data/...`) when a series is picked, so they stay current with its daily refresh and no API key is needed in the browser.
  - 80 monthly series from `data/long/<id>.csv`, history from January 2004 (or the series start), via FRED (Federal Reserve Bank of St. Louis) and credited to the original publisher: U.S. Bureau of Labor Statistics (PPI, CPI average prices, CES hourly earnings), International Monetary Fund (Primary Commodity Prices), U.S. Energy Information Administration, Federal Reserve Board (H.10 exchange rates), Cass Information Systems (Cass Freight Index). FRED series published daily or weekly are monthly averages.
  - 20 recent spot prices from `data/agency/spot.json` (about one year, daily, weekly or monthly as published): EIA Open Data and USDA Agricultural Marketing Service market news. These go through the same reader as uploads, so the time unit and seasonality are detected (weekly series with one year of data get no seasonality).
  - Blanks before the first or after the last value are dropped. A value the publisher skipped inside a series (October 2025 in two BLS CPI series) is filled by a straight line between its neighbours, the same rule Market Watch uses, and the page says so.
- `data/*.csv` (Cass shipments, corrugated boxes PPI, copper, jet fuel; Nov 2026 FRED snapshot, monthly from Jan 2018) are kept for the verification suite only.
- `SAMPLE_demand.csv` is **synthetic sample data** (trend + seasonality + noise, seed 42) from `make_sample.py`. Not real company data. It is the page's default series.

## Files
- `index.html`: the finished, self-contained page (GitHub Pages ready)
- `template.html`, `engine.js` (methods, backtest, metrics), `upload.js` (CSV/Excel reader, dates, time units), `mw.js` (loads and cleans Market Watch series), `app.js` (UI, SVG charts), `build.py` (inlines everything into index.html and builds the series catalog from a clone of the market-watch repo; set `MW_REPO`, default `../../market-watch`)
- `make_sample.py`, `data/*.csv`
- `dump_js.js`, `verify.py`: cross-check of the engine
- `test/dump_mw.js`, `test/verify_mw.py`: cross-check of the Market Watch loader (all 100 series, 24,432 values identical to an independent Python/numpy clean-up; the engine runs on every series with finite metrics)
- `research/`: the experiments behind the method choices (`compare_fit.py` vs statsmodels, `proto.py` + `score.py`)
- `preview/`: screenshots

Rebuild: `python3 build.py`. Verify: `node dump_js.js && python3 verify.py`, and `node test/dump_mw.js ../../market-watch > /tmp/mw.json && python3 test/verify_mw.py ../../market-watch /tmp/mw.json`.

## References
- Hyndman, R. J., & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.). OTexts. https://otexts.com/fpp3/
- Hyndman, R. J., & Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting, 22*(4), 679–688. https://doi.org/10.1016/j.ijforecast.2006.03.001
- Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: An analysis and review. *International Journal of Forecasting, 16*(4), 437–450. https://doi.org/10.1016/S0169-2070(00)00065-0
- Holt, C. C. (2004). Forecasting seasonals and trends by exponentially weighted moving averages. *International Journal of Forecasting, 20*(1), 5–10. https://doi.org/10.1016/j.ijforecast.2003.09.015
- Winters, P. R. (1960). Forecasting sales by exponentially weighted moving averages. *Management Science, 6*(3), 324–342. https://doi.org/10.1287/mnsc.6.3.324
- Box, G. E. P., & Jenkins, G. M. (1970). *Time Series Analysis: Forecasting and Control*. Holden-Day.
- Bates, J. M., & Granger, C. W. J. (1969). The combination of forecasts. *Operational Research Quarterly, 20*(4), 451–468. https://doi.org/10.2307/3008764
- Makridakis, S., Spiliotis, E., & Assimakopoulos, V. (2020). The M4 Competition: 100,000 time series and 61 forecasting methods. *International Journal of Forecasting, 36*(1), 54–74. https://doi.org/10.1016/j.ijforecast.2019.04.014
- Nelder, J. A., & Mead, R. (1965). A simplex method for function minimization. *The Computer Journal, 7*(4), 308–313. https://doi.org/10.1093/comjnl/7.4.308
- Assimakopoulos, V., & Nikolopoulos, K. (2000). The theta model: A decomposition approach to forecasting. *International Journal of Forecasting, 16*(4), 521–530.
- Hyndman, R. J., & Billah, B. (2003). Unmasking the Theta method. *International Journal of Forecasting, 19*(2), 287–290.
- Hoerl, A. E., & Kennard, R. W. (1970). Ridge regression: Biased estimation for nonorthogonal problems. *Technometrics, 12*(1), 55–67.
- Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. *Annals of Statistics, 29*(5), 1189–1232.
- Diebold, F. X., & Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics, 13*(3), 253–263.
- Harvey, D., Leybourne, S., & Newbold, P. (1997). Testing the equality of prediction mean squared errors. *International Journal of Forecasting, 13*(2), 281–291.
- Makridakis, S., Spiliotis, E., & Assimakopoulos, V. (2018). Statistical and machine learning forecasting methods: Concerns and ways forward. *PLOS ONE, 13*(3), e0194889.
- Makridakis, S., Spiliotis, E., & Assimakopoulos, V. (2022). M5 accuracy competition: Results, findings, and conclusions. *International Journal of Forecasting, 38*(4), 1346–1364.
- Gardner, E. S., Jr., & McKenzie, E. (1985). Forecasting trends in time series. *Management Science, 31*(10), 1237–1246. https://doi.org/10.1287/mnsc.31.10.1237
