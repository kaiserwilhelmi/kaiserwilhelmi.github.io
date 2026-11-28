# Iowa liquor demand forecast: freeze package

Built 2026-11-28 11:12 local time on Dawson's PC by the local session. Published to the site repository on Nov 28 2026 after Dawson's OK.

## Identity
- Protocol version: 1.10 (docs/evaluation-protocol.md, Nov 27 2026)
- Code version: SHA-256 over the sorted code-file hashes = `d54ee25561979eab1caa262acc66959519f7c6c4289d2e74bc67d9a9f0084c3d` (no git repository on the PC; every code file is in `code/` with its own hash)
- `unit_breaks.csv` SHA-256: `118a0818b3de1b038af398411e1d63a96141abaee6381d3d1ce2d5b81855c9a8` (expected `118a0818b3de1b038af398411e1d63a96141abaee6381d3d1ce2d5b81855c9a8`: match)
- Environment: Python 3.12.16, pandas 3.1.1, numpy 2.5.5, lightgbm 4.7.0, statsmodels 0.15.0, scipy 1.18.1, duckdb 2.0.1
- Raw yearly files: 15 zips and 15 parquet files re-hashed now; all zips match the download manifest: True; all parquet files match: True (`raw_files_sha256.csv`)

## Notes
- Published forecast: layer c (equal-weight average of the per-series statistical pool and the global tree model), uncalibrated, calibration window 12 (ruling-04). Live origin 2026-10, horizons Nov 2026 to Jan 2027. Expected Iowa store orders (depletions).
- Layer d (c with conformal calibration) is frozen beside it as `forecasts/forecast_live_challenger_d.csv`, labelled 'challenger, not the published forecast'. It switches only if it passes section 9 on 12 final-graded live months.
- 2025 test (judging year): a 0.2820, b 0.2433, c 0.2258, d 0.2215 (mean h1-3, WSPL). d beat c by 1.90%, under the 2% margin. 2026 test, run once on c: 0.2423. Coverage of c fails section 5 and is stated, not fixed: 2025 pooled 90.9 / 56.8; see `forecasts/coverage_note_data.csv`.
- Tuning: tree trial 3 of 40 adopted (+5.96%, better in 2023 and 2024 separately), base features, Tweedie 1.1; SBA/TSB alpha 0.3 per class, ADIDA length 2 for intermittent. 5 of 24 final tree models stop at the 2,000-round cap (reported; cap not raised).
- Liters: 302 flagged series not hand read by the freeze default to unknown (ruling-04 item 5). Liters cover 93.16% of trailing-12 dollars; 644 series left out. 84207 stays unknown. Units are never summed above the product; level liters are labelled partial.
- units_tiers.py was made deterministic at this freeze: category and description now follow the same most-bottles rule as the models, and trailing-12 sums are rounded to cents. Before, ties were broken differently between runs. Effect against checkpoint 03: flagged series 647 -> 648, standard-tier series at 200 ml or less 115 -> 113 ($12.94M, 3.09%).
- MKL: every stage 2 script sets MKL_THREADING_LAYER=SEQUENTIAL before numpy loads (MKL's OpenMP layer crashed with 0xc06d007f in this environment). No package was installed for this.
- stage1/backup_pre62/ was overwritten with then-current files by the local session while backing up (reported in checkpoint 02). It does not hold the pre-decision-62 state; that state is not recoverable from it.
- 00_download_and_pack.py is not on this PC (searched C:\ds and Claude_Allowed). The download itself is documented by `raw_provenance/download_log.txt`, `manifest.csv` and `convert_results.jsonl`, and every raw zip and parquet file is re-hashed in `raw_files_sha256.csv`.
- Not in the package (too large, rebuildable from the code): stage1/iowa_liquor.duckdb (12 GB), stage2/layers.parquet (149 MB), member and tree fit files.
- Level ranges: direct ETS ranges for state, category and brand, calibrated in time order; rows that are not calibrated carry no range. At the live origin the bottom-up sum falls outside the level's own 50% range in 212 of 720 level-horizons; both are shown.
- The public commit is made by the design thread only after Dawson's OK on this file list. Nothing has been pushed or posted.

- Redaction at publication (Nov 28 2026, design thread, with Dawson's OK): the Windows user folder path in 4 files (code/build_nb.py, code/stage2_s2eval.py, cleaning/01_stage1_demand_tables.ipynb, docs/HANDOFF.md) was replaced with `<home>`. Their sizes and SHA-256 values in this manifest are the redacted files. Original hashes: cleaning/01_stage1_demand_tables.ipynb `33f066137f2f5f190413d46497fb214fa8ee30559c678f5583cfd35e84e778f0`; docs/HANDOFF.md `9e24608be6825eeb26bf6bcb50d2e7a3602827b8e0ccf0c5c1fba771e9ef3f82`; code/build_nb.py `d6b120c3f1b8abb0a19e2104de7f1f6626eeccfa8ac7f8e6e8c40701383ab7b7`; code/stage2_s2eval.py `aec6145cd39cad49c8bcba2f9411f6e4f4408736cc5c718a77982747f53330f2`. No forecast, map, cleaning or result file was changed.

## Files

| file | bytes | SHA-256 |
|---|---:|---|
| forecasts/forecast_live.csv | 5,044,916 | `f163c174c5cf18fba08a841346370a13440e09fa087afedca5fd77c48fd5caba` |
| forecasts/forecast_live_levels.csv | 202,194 | `b63d77d40873a6322f646ae87b2632089a00ebb68b009c3291c13847aebd05cb` |
| forecasts/forecast_live_challenger_d.csv | 5,342,065 | `eb05adbd143949dc22cc436201359e9fd7a748a2589f6f214db20cdbeb2653e2` |
| forecasts/grading_rules.json | 325 | `b30128c43874d6b9203a34aab5dcc5f8720a9e38616cabf97acc8070e5850405` |
| forecasts/coverage_note_data.csv | 1,524 | `ddc60842513872683c0de1283a4ee551b39f9a64614bf1b9194da5b66f50ab83` |
| maps/product_list.csv | 784,616 | `fd1dd72cdc8a367e8966613f07a2e083fdd44a7883e81e6111b3792fe1645661` |
| maps/brand_map.csv | 1,378,996 | `ce779896c9d437f0a62867ccc781c035a656d364ef6bfa994408d275ec42e533` |
| maps/item_series.csv | 1,730,876 | `3ef3485a501a4ca75273a18cf03523c4fa21cdbba3ac4eff8361d189bfbf79e9` |
| maps/series_chains.csv | 42,039 | `4f68bc57e462ea844f390e2f5067f461fadb66893bac4b68e79237c9ba76509b` |
| maps/item_vendor.parquet | 144,548 | `de03ab2d0027f583a48a72ff7d1171873b6f4fd87a9733160449a3c6650d30c9` |
| maps/product_dim.parquet | 793,209 | `b1505cc96922845696b722ca20189e177bc9d33dedf406e3a0b2a870bc766384` |
| maps/store_dim.parquet | 118,059 | `edca64f653fb9e8003357428008a8f4065d3c5740223385f157023868c43fcb2` |
| cleaning/01_stage1_demand_tables.ipynb | 439,052 | `6ba864b250d26116cb2761f929cb75eb88e1f0d19001fcaa98e833cd22eee25b` |
| cleaning/unit_breaks.csv | 11,393 | `118a0818b3de1b038af398411e1d63a96141abaee6381d3d1ce2d5b81855c9a8` |
| cleaning/unit_breaks_applied.csv | 6,226 | `4c2af9904c1845b04f7fd9490df0346b0a31ba4fa3e6175003275004e3715018` |
| cleaning/unit_date_cuts.csv | 39 | `75008bda066aebaef2ffde03f19595ed61a56dc52caa2478bf1c9b8aab826654` |
| cleaning/links_removed_by_price_guard.csv | 2,156 | `29da1b80f7d66b0850b4921b0c40705b91f3e204262fe0b23f2573110d638a72` |
| cleaning/holiday_bottles_by_year.csv | 6,758 | `cdf350e4349645638cd7b23878c8f9dbb77fcd87464f0af26e0e5c2801769847` |
| cleaning/october_completeness_tests.csv | 144 | `4e252b72607fff974f15fde576d8d411f2e7b5e50c85685db670f46b9295751f` |
| cleaning/evidence_zero_lines_by_year.csv | 444 | `38f6c8833cbfb6e12703e3c6f267a4e17609aa0d4decde3207b5c9c01420f465` |
| units/units_table.csv | 24,215 | `7bf1d2308a3dfdca9b7cfaee36549d13808fe7c75bd8994deb27c5e745b8f944` |
| units/units_series_t12.csv | 1,230,996 | `63c10480df67e34b3bb4b94c0b9c4e5468f0513f196511f14e0f5abaa25b31a7` |
| units/units_lines_factor.parquet | 250,635 | `668bbd3fd0715b1a4a1b1d0a81d262fc2167615da4980d3af8e1c6ac2426f267` |
| units/units_decision66_checks.csv | 762 | `c7be4b49af911307811a630d9017d5234378615775bc369c3556dae47c961da6` |
| units/units_tiers_hand_read.csv | 96,557 | `5f8fd6451b78b0df23f2149b2c30828466926b5232cd448cddc31ef0fb866585` |
| addendum5/addendum5_brand_hand_share.csv | 912 | `c7e1158ba05b29d46792246f779fc0e2f43ea5538ca52a8f4c7bf77e02539ccd` |
| addendum5/addendum5_price_outliers.csv | 19,739 | `db3594172add618832d6030e5eda5229a579439ef8433868085b8096a8b6fcb4` |
| addendum5/addendum5_reverse_check.csv | 87 | `bfb319a243b30d0cd5fa1870b39c03561e9d3f6ae89968d2e8885df64e5c5c08` |
| addendum5/addendum5_rule_only_for_hand_check.csv | 72 | `9d3096237b04596a770c2d80cc50112951fe488443e19a3c7cc3cd8eebec80b3` |
| addendum5/addendum5_size_changes.csv | 31,009 | `9a313fa6a9fd7bdae33fcf561e7fab9cf8e8e4c9d88d6a634e8d55f1a699d15b` |
| addendum5/addendum5_units_evidence.csv | 657 | `0005040b036d60dd721ffc14d3f3982e99e5fa8ffd9ddee82ec42f88c941d374` |
| addendum5/addendum5_log.txt | 10,972 | `7ed884cf0ea665ec50690885c9b22d48afc2d115388c0fa54a660cd14d70a49d` |
| model/chosen_layer.json | 86 | `ce2d439117eac27d58b0250e7383e940131258278f50d4f1abe12ef2af933987` |
| model/chosen_config.json | 440 | `ad31c0136889fe4337911548a43197e0d1851699c36d596c1767942615ff93e7` |
| model/rounds_fixed.json | 428 | `621991eb8ebcd391adc335eebf4df5e129dcf2c92fd04ed689064796e75a3b34` |
| model/trials.csv | 16,339 | `62ef3b053658f17fe199253e83879d582392587584b2f5dd6ec3abe8a4f25f0e` |
| model/stat_params.json | 329 | `5b39b72ead84bbacad00c39cbb5df70c8e9818260f25ac15c4653a35d1266291` |
| model/stat_tune_results.csv | 6,178 | `e67ce8e40c3e9cc73ae4ea97cebee9980cf941e774ff0c146ecbbea2140f6ac7` |
| model/stat_tune_choices.csv | 465 | `1908db4b1c51de780b4ec0683e1c4a3f382695f23eb6445b4698dff96d61664e` |
| results/metric_summary_2023_24.csv | 1,668 | `bebef22872d7599d9a5fca5a4d5877ed39f9805ac3c43d43088c68631b86ce95` |
| results/metric_2025.csv | 33,755 | `7efc1e828062a06670edfd5096c3d5c19e1aab293f5eb94dbe731a03b6b58de3` |
| results/layer_tests_2025.csv | 284 | `ede315c5830e4bbf524933ab4446ad5037f00cc4b7ebcf2ecc6c16631d35fe25` |
| results/coverage_2025.csv | 14,080 | `e7aa2b388c03f67c19252769c785be9a2f6b95f92271b046f9a428be0f1fc722` |
| results/test_2026.csv | 408 | `1351884b73edf7fc930b1f92b0b2b1f70f3c699781d2548704c7ee0ccc5872c1` |
| results/coverage_2026.csv | 1,121 | `f7bd49f7dc229b241774c76c2b8574245b11ef65104cee482dab6c5c12b2de5f` |
| results/flagged_scores_2023_24.csv | 37,420 | `bb175b1755b9657499f7891c8ed012352655e9278b847cef83dccb8526aa6d94` |
| results/flagged_scores_2025.csv | 18,742 | `b863c29932d8e02b0ecf5310ccf70a283d6bb5bf061fc26059036d1f02773a2c` |
| results/flagged_scores_2026.csv | 3,932 | `730b388bd899e239d8f6691293a3593f84b67b65f9d116c1937b360227ece8ff` |
| results/unit_breaks_2025_26.csv | 470 | `c9a39b026b5b9d015df17894ee25c47e3309182ee0be53c0be4e12adf5b65370` |
| results/levels_forecasts.parquet | 2,948,180 | `53b443dd9092b6528ab0da80348a9a7232397fe6299364e2853f5e9c89d0f29f` |
| results/watch_list_scores.csv | 1,059 | `c9d398a3771c8e6353e6e2bfc4d5dfac6d9b7ec89ccb197aa83bd06ec0b3d678` |
| results/june_diagnostic.csv | 1,752 | `0ca7de580d112c26f20076c10037686288f341cc3145c4bfe62e9329fcfe0d03` |
| docs/evaluation-protocol.md | 25,515 | `dd318490d400787a69592befb34ded4ffed6fe3ac8ad7f88671c62ed1f253d92` |
| docs/decision-log.md | 54,953 | `4d6c2ab7706cfe9eda738eca7541421f21d9b3f935e416165e08ceb74d392fcb` |
| docs/HANDOFF.md | 13,274 | `f9e5d640d4ea7b579f6fa572ebe889f9269ac472fa17ccd62f9160794eefcae3` |
| docs/ruling-01b-amend.md | 2,414 | `e8e5b91b38ffe6b020ba602bcfa03e9bb7e830f51b6d6abcf579e60f056b19e6` |
| docs/ruling-01b-amend2.md | 1,007 | `a51768dc7429fbe8c7f98c8f8e04b6fafe6388da53db2eccb0b9ea30d616c757` |
| docs/ruling-01b.md | 3,596 | `b88d4dfaefdc14d1899dd791599e6d7437cec10f1ce8eddefa23bb6084b5eec0` |
| docs/ruling-01d-amend.md | 1,696 | `ccf33e7df4be70084572a65c579d7c1415e2c01a1a6c7107b588294748836eda` |
| docs/ruling-01d.md | 3,755 | `7e381f80ea29f2e149bd6ffb8d7a6d14fd397a09a78e8d4d3cfe555d50178c00` |
| docs/ruling-01e-amend.md | 3,425 | `f5287ca37386ddd51fc786d48b07df7f198a8c57d23f06b686f85b26b68eb0cb` |
| docs/ruling-01e.md | 2,106 | `5f2a0e46143e4a5c3628d577958b56954756e68917b97d0bc973916d82e4b891` |
| docs/ruling-02-resume.md | 1,282 | `55b3a2695cf2bed0384532095babde8a9ec1c5f8dc6ca0fd48d3fbef5be357f5` |
| docs/ruling-04.md | 2,408 | `07c85cee1443ab75c82e967658e584b54f45a2d5b7fa7466216c9452866bdcbd` |
| raw_provenance/manifest.csv | 7,380 | `e515e6500017317a75dc08199c5aff42966c20b0e5965470e5f55214a239f84a` |
| raw_provenance/download_log.txt | 1,211 | `f6d5a0f3bf0b1e5195eb089aec101cdfa5209a7c4938b1641f6d85d5f5cf4ce7` |
| raw_provenance/convert_results.jsonl | 14,994 | `89948f89a75b7bd23741b240adf7089474a98e5041925a02e89766bbf5322f6c` |
| code/build_nb.py | 129,427 | `40f6bf8e16e8a58dde17da8d94473c733bd241d20f4e1c91e0acf22b6657f91d` |
| code/verify_stage1.py | 30,939 | `a6ab6c9f767ac76fd1f7319fc35a9ddcb57a4cadd2d0b038c24cec5f3b85b693` |
| code/build_freeze.py | 6,117 | `0a6b51df255386caecb02f927fbaf0281d5dfe0f7e63df632330287a1b863e4a` |
| code/stage2_addendum5.py | 10,006 | `ba87c13613bf54c31a554be52d2eee83687e1b6c7350bbf29c22f33b588ee743` |
| code/stage2_brand_map.py | 11,892 | `6843bad547db586806dc3b37a1c3eae0259219b65f4615b1f93995cbe6c8ba62` |
| code/stage2_data_reads.py | 3,027 | `2617f59f13a17df0da345f782532b14ff18a2a623d042201d9f1ae2f5645c447` |
| code/stage2_handcheck_breaks.py | 5,657 | `21aef23c77edeaadcf973eb6d2b327fbb311f0f5c833fcc891178b4846da6901` |
| code/stage2_june_diag.py | 2,614 | `4be1083ba4901e62fcff96b48e9fd2fd6c1e8a4869ad37d5ba401898d9a5366c` |
| code/stage2_make_hand_extra.py | 724 | `a19cffbf8860c9182faeb2f6ae5d32bc8d7e3148f03d2a7f14a2c0d0d337f75c` |
| code/stage2_report_03.py | 10,634 | `27917a62f5e5700eb9c2235ec765b89ada1fa28ebb5b04bb786b86081a55d96d` |
| code/stage2_report_03_units.py | 6,598 | `9c83f7f04f4a9dbac6d0eaeb2d7fabf54076d19d7185f6b99541826432f167d9` |
| code/stage2_report_04.py | 5,624 | `1a938654e8e3fffc7cb24ebd49342741583a535f91cf9bea744bce18a951fe91` |
| code/stage2_s2common.py | 13,776 | `786860b5ae83e0f1ad901a33e842fd94c6664e563b36e397e6517680c99fe8a9` |
| code/stage2_s2eval.py | 13,545 | `72714cebcfde38b08885d9a8970f4c7943e5198d658ab6667131bbacaa0da0cd` |
| code/stage2_s2freeze_extras.py | 4,050 | `21ba7f7e457f1c7f4dec16c5a3c8d1a00a547fc009c09b106675c04ecf44f8bd` |
| code/stage2_s2levels.py | 6,724 | `cad9623e3b3a5bc6de740374641b0d62ef34a9d660f84f585efc1faa5696831e` |
| code/stage2_s2live.py | 9,871 | `1d6d41e2ec57486b09be7376d50b39d6b09aad21a0ab4141ce9d1cabe46a3e74` |
| code/stage2_s2stat.py | 10,963 | `550cda8fef1c312e95170bf0308e98ab631b3890662ac4288761137e29461d00` |
| code/stage2_s2stat_tune.py | 6,016 | `3b08ace359295e64fad654866037f372480a5230a891ae833b499ae7578f0973` |
| code/stage2_s2tree.py | 21,279 | `db53eeb59af6aa6b82d47f4632bd6b6edb5e8c9e4cc9c516fa7b6c69e8af359c` |
| code/stage2_second_reader.py | 3,793 | `0ab687c6ec608be658f99e2c412f2b65c1af4a511c180239dff055e12bf7cfba` |
| code/stage2_second_reader_followup.py | 8,312 | `e67104864c87774ce08d43dc0e4838b8d4f1c01ca90721e9049b92618c629922` |
| code/stage2_top100_moves.py | 2,367 | `27908a4acdf8b2c16ebb93d31f7cd39595d53329090062c9fbefca86b1614f34` |
| code/stage2_trials_read.py | 2,505 | `20da93598bdfc101630c400e77c89a38a0f76621982e73e726602c859225d375` |
| code/stage2_truncation_test.py | 2,522 | `5596a3bf2e4e48ed74dd3ba4eba527fefa1b08f50579972c8dbdae0152fd1a3e` |
| code/stage2_truncation_test_tree.py | 2,467 | `5a816d29cbe3a1dad38c541f7d4b1d95ff1da9ec3a36e505e7edbf0ed0d12415` |
| code/stage2_unit_steps.py | 3,518 | `baac5e712658c9e7498092df9d6fbe1ec66552e78f8579a19c3776b4d69db782` |
| code/stage2_units_tiers.py | 18,472 | `c177a4d4870efcd070b11e8622987bdd539cd9471190abd8a3bb1cb8a61b03f0` |
| code/stage2_watch_list.py | 1,504 | `1b55826f16907b89fac402257e7dc0b292a712145069ff24f22735daf41e489a` |
