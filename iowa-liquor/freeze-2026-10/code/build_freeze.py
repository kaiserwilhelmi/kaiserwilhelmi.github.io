"""Freeze package (HANDOFF step 7, ruling-04 item 7). Copies the frozen files into <base>/freeze/, hashes every file
and every raw yearly file (re-hashed now and compared with the download manifest), and writes MANIFEST.md and
manifest_files.csv. Nothing is pushed or posted. Usage: python build_freeze.py <base> <notes json>"""
import hashlib, json, shutil, sys, platform
from datetime import datetime
from pathlib import Path
import pandas as pd

base = Path(sys.argv[1]); notes = json.load(open(sys.argv[2], encoding="utf-8"))
F = base / "freeze"
if F.exists():
    sys.exit("freeze/ already exists; move it aside first (no files are deleted by this script)")
s1, s2, docs = base / "stage1", base / "stage2", base / "docs"
PLAN = {
    "forecasts": [s2 / "forecast_live.csv", s2 / "forecast_live_levels.csv", s2 / "forecast_live_challenger_d.csv",
                  s2 / "grading_rules.json", s2 / "coverage_note_data.csv"],
    "maps": [s2 / "product_list.csv", s2 / "brand_map.csv", s1 / "item_series.csv", s1 / "series_chains.csv",
             s1 / "item_vendor.parquet", s1 / "product_dim.parquet", s1 / "store_dim.parquet"],
    "cleaning": [base / "01_stage1_demand_tables.ipynb", s1 / "unit_breaks.csv", s1 / "unit_breaks_applied.csv",
                 s1 / "unit_date_cuts.csv", s1 / "links_removed_by_price_guard.csv", s1 / "holiday_bottles_by_year.csv",
                 s1 / "october_completeness_tests.csv", s1 / "evidence_zero_lines_by_year.csv"],
    "units": [s2 / "units_table.csv", s2 / "units_series_t12.csv", s2 / "units_lines_factor.parquet",
              s2 / "units_decision66_checks.csv", s2 / "units_tiers_hand_read.csv"],
    "addendum5": sorted(s2.glob("addendum5_*.csv")) + [s2 / "addendum5_log.txt"],
    "model": [s2 / "chosen_layer.json", s2 / "tree" / "chosen_config.json", s2 / "tree" / "rounds_fixed.json",
              s2 / "tree" / "trials.csv", s2 / "stat_params.json", s2 / "stat_tune_results.csv", s2 / "stat_tune_choices.csv"],
    "results": [s2 / "metric_summary_2023_24.csv", s2 / "metric_2025.csv", s2 / "layer_tests_2025.csv",
                s2 / "coverage_2025.csv", s2 / "test_2026.csv", s2 / "coverage_2026.csv", s2 / "flagged_scores_2023_24.csv",
                s2 / "flagged_scores_2025.csv", s2 / "flagged_scores_2026.csv", s2 / "unit_breaks_2025_26.csv",
                s2 / "levels_forecasts.parquet", s2 / "watch_list_scores.csv", s2 / "june_diagnostic.csv"],
    "docs": [docs / "evaluation-protocol.md", docs / "decision-log.md", docs / "HANDOFF.md"] + sorted(docs.glob("ruling-*.md")),
    "raw_provenance": [base / "manifest.csv", base / "download_log.txt", base / "convert_results.jsonl"],
    "code": [base / "code" / n for n in ("build_nb.py", "verify_stage1.py", "build_freeze.py")] + sorted((base / "code" / "stage2").glob("*.py")),
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


missing = [str(p) for ps in PLAN.values() for p in ps if not p.exists()]
if missing:
    sys.exit("missing files: " + "; ".join(missing))
rows = []
for sub, ps in PLAN.items():
    (F / sub).mkdir(parents=True, exist_ok=True)
    for p in ps:
        dst = F / sub / (("stage2_" + p.name) if sub == "code" and p.parent.name == "stage2" else p.name)
        shutil.copy2(p, dst)
        rows.append(dict(path=str(dst.relative_to(F)).replace("\\", "/"), bytes=dst.stat().st_size, sha256=sha(dst),
                         source=str(p.relative_to(base))))
M = pd.DataFrame(rows)
# raw yearly files: re-hash now, compare with the download manifest
man = pd.read_csv(base / "manifest.csv")
raw = []
for r in man.itertuples():
    z = base / "raw" / f"iowa_liquor_sales_{r.year}_{r.dataset_id}_rows.zip"; pq = base / "parquet" / r.parquet_files
    zs, ps = sha(z), sha(pq)
    raw.append(dict(year=r.year, zip=z.name, zip_sha256=zs, zip_matches_download=zs == r.zip_sha256,
                    parquet=pq.name, parquet_sha256=ps, parquet_matches_download=ps == r.parquet_sha256))
R = pd.DataFrame(raw)
R.to_csv(F / "raw_files_sha256.csv", index=False)
code_ver = hashlib.sha256("".join(M[M.path.str.startswith("code/")].sort_values("path").sha256).encode()).hexdigest()
M.to_csv(F / "manifest_files.csv", index=False)
ub = M[M.path == "cleaning/unit_breaks.csv"].sha256.iat[0]
try:
    import lightgbm, numpy, statsmodels, duckdb, scipy
    env = (f"Python {platform.python_version()}, pandas {pd.__version__}, numpy {numpy.__version__}, lightgbm {lightgbm.__version__}, "
           f"statsmodels {statsmodels.__version__}, scipy {scipy.__version__}, duckdb {duckdb.__version__}")
except Exception as e:
    env = f"(versions not read: {e})"
L = [f"# Iowa liquor demand forecast: freeze package", "",
     f"Built {datetime.now():%Y-%m-%d %H:%M} local time on Dawson's PC by the local session. Not pushed or posted.", "",
     "## Identity",
     f"- Protocol version: {notes['protocol_version']}",
     f"- Code version: SHA-256 over the sorted code-file hashes = `{code_ver}` (no git repository on the PC; every code file is in `code/` with its own hash)",
     f"- `unit_breaks.csv` SHA-256: `{ub}` (expected `{notes['unit_breaks_sha256']}`: {'match' if ub == notes['unit_breaks_sha256'] else 'MISMATCH'})",
     f"- Environment: {env}",
     f"- Raw yearly files: {len(R)} zips and {len(R)} parquet files re-hashed now; all zips match the download manifest: "
     f"{bool(R.zip_matches_download.all())}; all parquet files match: {bool(R.parquet_matches_download.all())} (`raw_files_sha256.csv`)", "",
     "## Notes"] + [f"- {n}" for n in notes["notes"]] + ["", "## Files", "",
     "| file | bytes | SHA-256 |", "|---|---:|---|"] + [f"| {r.path} | {r.bytes:,} | `{r.sha256}` |" for r in M.itertuples()]
(F / "MANIFEST.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"freeze: {len(M)} files, {M.bytes.sum() / 1e6:.1f} MB; raw zips match {bool(R.zip_matches_download.all())}, "
      f"parquet match {bool(R.parquet_matches_download.all())}; unit_breaks hash {'match' if ub == notes['unit_breaks_sha256'] else 'MISMATCH'}")
