"""Read stage2/tree/trials.csv robustly. The header was written by the first (timing) row, before score_excl_window
existed, so later rows carry one or two more fields than the header. Fields are mapped by position:
... lambda_l2, score_h1_3, score_2023, score_2024, [score_excl_window], seconds, rounds, [mean_sq_error].
Usage as a module: read_trials(path) -> DataFrame. As a script: python trials_read.py <base> (independent check of the
section 6a adoption rule, printed short)."""
import csv, json, sys
from pathlib import Path
import pandas as pd

HEAD = ["trial", "feature_set", "half", "num_leaves", "min_data_in_leaf", "learning_rate", "feature_fraction",
        "bagging_fraction", "lambda_l2", "score_h1_3", "score_2023", "score_2024"]


def read_trials(f):
    rows = []
    with open(f, newline="") as fh:
        rd = csv.reader(fh); next(rd)
        for r in rd:
            d = dict(zip(HEAD, r[:12])); rest = r[12:]
            if len(rest) == 2:                       # timing row: seconds, rounds
                d.update(score_excl_window=None, seconds=rest[0], rounds=rest[1], mean_sq_error=None)
            else:
                d.update(score_excl_window=rest[0], seconds=rest[1], rounds=rest[2],
                         mean_sq_error=rest[3] if len(rest) > 3 else None)
            rows.append(d)
    df = pd.DataFrame(rows)
    for c in HEAD[3:] + ["score_excl_window", "seconds", "mean_sq_error"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


if __name__ == "__main__":
    base = Path(sys.argv[1]); t = read_trials(base / "stage2" / "tree" / "trials.csv")
    t0 = t[t.trial == "featureset_base"].iloc[-1]
    rnd = t[t.trial.str.fullmatch(r"\d+")].copy(); rnd["n"] = rnd.trial.astype(int)
    b = rnd.loc[rnd.score_h1_3.idxmin()]
    gain = 1 - b.score_h1_3 / t0.score_h1_3
    adopt = gain >= 0.01 and b.score_2023 < t0.score_2023 and b.score_2024 < t0.score_2024
    tw = t[t.trial.str.startswith("tweedie")]
    print(f"random trials {len(rnd)}; best {b.n} {b.score_h1_3:.4f} vs start {t0.score_h1_3:.4f}; gain {100*gain:.2f}%; "
          f"2023 {b.score_2023:.4f}<{t0.score_2023:.4f} 2024 {b.score_2024:.4f}<{t0.score_2024:.4f}; adopt {adopt}; "
          f"tweedie best {tw.loc[tw.mean_sq_error.idxmin(), 'trial']}")
    cfg = json.load(open(base / "stage2" / "tree" / "chosen_config.json"))
    same = all(abs(float(b[k]) - float(v)) < 1e-9 for k, v in cfg["settings"].items())
    print(f"chosen_config matches best trial settings: {same}")
