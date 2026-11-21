# Forecast Method Comparison

**Business question:** Which forecasting method should a buyer trust for a given demand or price series, and how wrong is it likely to be?

The page backtests up to eleven methods on a series with a rolling origin, scores them on seven error measures, and lets the data pick the winner. No method is favoured in advance. It also checks whether the winner holds up when the backtest window changes (12, 24, 36 periods). Pick a built-in series or upload your own CSV (`date,value`, oldest first). Everything runs in the browser; uploaded files never leave it.

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
| Combination: average of Holt-Winters + seasonal ARIMA (seasonal data) | Bates & Granger (1969); Makridakis et al. (2020) |
| Combination: average of SES + Holt + damped (no seasonality; the M4 "Comb" benchmark) | Makridakis et al. (2020) |

**Fitting.**
- Holt-Winters: α, β, γ and the starting level, trend and m seasonal terms are fitted together by minimising one-step squared error with a Nelder–Mead search (Nelder & Mead, 1965). This is the least-squares version of the ETS(A,A,A) fit in FPP3.
- Seasonal ARIMA: θ and Θ fitted by conditional sum of squares (Nelder–Mead).
- SES / Holt / damped: weights from a grid (α, β ∈ {0.05, …, 0.95}; φ ∈ {0.80, …, 0.98}). Full optimisation changed their accuracy by under 1% on these series, so the simpler, faster fit was kept.

**Why these choices (tested before building).** On the five series (24-month window, 6 steps ahead), fitting Holt-Winters' starting states lowered its average MASE from 0.581 to 0.498, and seasonal ARIMA was the best method on both real seasonal series. Accuracy matches the statsmodels maximum-likelihood fits closely (Cass freight: Holt-Winters 0.408 here vs 0.404; seasonal ARIMA 0.393 vs 0.404). A nested test (choose the method on an older 24-month window, score it on the newest 12 months) beat the naive forecast on every series, which supports letting the backtest choose.

## Evaluation
- **Rolling origin** (Tashman, 2000; FPP3 §5.10): for each of the last N periods (12/24/36), every method is re-fitted on data before that point and forecasts 1..h steps ahead (h = 1/3/6/12). Forecasts that fall inside the data are scored, pooled across horizons. MAE by horizon is also shown.
- **Metrics:** MAE, MSE, RMSE, MAPE, sMAPE, MASE, Bias (mean error = actual − forecast). MAPE is reported as n/a if any actual is zero.
- **MASE scale** (Hyndman & Koehler, 2006): in-sample MAE of the seasonal-naive forecast (naive if seasonality = none) on the training data before the first origin. Note that multi-step errors are compared with a one-step scale, so MASE > 1 is normal at longer horizons.
- **Winner:** lowest MASE (RMSE breaks ties). The recommendation flags near-ties, small gains over naive (< 5%), disagreement between metrics, bias, and whether the winner is stable across 12/24/36-period windows.
- **Speed:** every method is fitted once per origin (longest window, 12 steps ahead); each horizon/window setting is then scored from those forecasts. A k-step forecast doesn't depend on how many steps were requested, so this is exact.

## Verification
`verify.py` is an independent Python re-implementation (regression via numpy least squares, a different solver from the JS). `node dump_js.js` runs `engine.js` over 5 series × 2 seasonality settings × 3 windows × 4 horizons (120 cases); `python3 verify.py` compares every metric, MAE-by-horizon value, 12-step future forecast, fitted parameter and the winner at each window: **30,330 values, worst relative difference 1.8e-10, all winners identical.** The Python check uses plain left-to-right sums because Python 3.12+ `sum()` is compensated and would make the optimiser drift from JavaScript's.

## Data (snapshot Nov 2026, monthly from Jan 2018)
- Cass Freight Index: Shipments (FRGSHPUSM649NCIS), NSA, index Jan 1990 = 1. Cass Information Systems, Inc., via FRED (Federal Reserve Bank of St. Louis).
- PPI by Industry: Corrugated and Solid Fiber Box Mfg (PCU322211322211), index Mar 1980 = 100. U.S. Bureau of Labor Statistics, via FRED.
- Global price of Copper (PCOPPUSDM), $/metric ton. International Monetary Fund, via FRED.
- Kerosene-Type Jet Fuel Prices: U.S. Gulf Coast (DJFUELUSGULF), $/gal, monthly average of daily. U.S. Energy Information Administration, via FRED.
- `SAMPLE_demand.csv` is **synthetic sample data** (trend + seasonality + noise, seed 42) from `make_sample.py`. Not real company data.

## Files
- `index.html`: the finished, self-contained page (GitHub Pages ready)
- `template.html`, `engine.js` (methods, backtest, metrics), `app.js` (UI, SVG charts), `build.py` (inlines everything into index.html)
- `make_sample.py`, `data/*.csv`
- `dump_js.js`, `verify.py`: cross-check
- `research/`: the experiments behind the method choices (`compare_fit.py` vs statsmodels, `proto.py` + `score.py`)
- `preview/`: screenshots

Rebuild: `python3 build.py`. Verify: `node dump_js.js && python3 verify.py`.

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
- Gardner, E. S., Jr., & McKenzie, E. (1985). Forecasting trends in time series. *Management Science, 31*(10), 1237–1246. https://doi.org/10.1287/mnsc.31.10.1237
