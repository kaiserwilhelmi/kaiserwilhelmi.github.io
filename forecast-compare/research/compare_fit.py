import warnings, json, numpy as np
warnings.filterwarnings("ignore")
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA
import verify as V
H, TEST, M = 6, 24, 12
FILES = ["SAMPLE_demand", "FRGSHPUSM649NCIS", "PCU322211322211", "PCOPPUSDM", "DJFUELUSGULF"]

def ets(kind):
    def f(y):
        y = np.asarray(y)
        if kind == "ses": mdl = ExponentialSmoothing(y, initialization_method="estimated")
        if kind == "holt": mdl = ExponentialSmoothing(y, trend="add", initialization_method="estimated")
        if kind == "damped": mdl = ExponentialSmoothing(y, trend="add", damped_trend=True, initialization_method="estimated")
        if kind == "hw": mdl = ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=M, initialization_method="estimated")
        return list(mdl.fit().forecast(H))
    return f

def auto_arima(y):
    best = None
    for d in (0, 1):
        for p in range(3):
            for q in range(3):
                try:
                    r = ARIMA(np.asarray(y), order=(p, d, q), trend="c" if d == 0 else "t").fit()
                    if best is None or r.aicc < best.aicc: best = r
                except Exception: pass
    return list(best.forecast(H))

def airline(y):
    return list(ARIMA(np.asarray(y), order=(0, 1, 1), seasonal_order=(0, 1, 1, M)).fit().forecast(H))

def mase(y, fn):
    n = len(y); first = n - TEST
    scale = np.mean([abs(y[t] - y[t - M]) for t in range(M, first)])
    errs = []
    for T in range(first, n):
        f = fn(y[:T])
        errs += [abs(y[T + k - 1] - f[k - 1]) for k in range(1, H + 1) if T + k - 1 < n]
    return np.mean(errs) / scale

js = {c["file"]: c for c in json.load(open("js_results.json")) if c["m"] == 12 and c["test"] == TEST and c["h"] == H}
out = {}
for f in FILES:
    path = "data/" + f + ".csv"; y = V.load(path)
    g = {r["id"]: r["metrics"]["MASE"] for r in js[path]["results"]}
    row = {"grid": {k: g[k] for k in ("ses", "holt", "damped", "hw")}, "best_grid_tool": min(g, key=g.get), "best_grid_mase": min(g.values()),
           "mle": {k: mase(y, ets(k)) for k in ("ses", "holt", "damped", "hw")},
           "auto_arima": mase(y, auto_arima), "airline_sarima": mase(y, airline)}
    out[f] = row; print(f, json.dumps(row, default=float))
json.dump(out, open("compare_fit.json", "w"), default=float, indent=1)
