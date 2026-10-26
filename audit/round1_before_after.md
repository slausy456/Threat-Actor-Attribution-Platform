# Fusion rules: before and after

Dataset and method: the 72 synthetic personas produce 2,556 possible pairs (24 same-actor and 2,532 different-actor). Overall classification metrics use every possible pair and actor membership from the answer key only after scoring. Scenario metrics use the 53 labelled pairs in `data/synthetic/ground_truth.json`. The before run used the original scoring; the after run used the fusion rules on branch `fusion-rules`. Both used the bundled persona data and the same `audit/accuracy_check.py` evaluator. Confidence comparisons use the displayed, capped `confidence` field.

## Overall threshold metrics

| Run | Cutoff | TP | FP | TN | FN | Precision | Recall | False-positive rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Before | 0.90 | 20 | 0 | 2,532 | 4 | 1.000 | 0.833 | 0.000 |
| After | 0.90 | 17 | 0 | 2,532 | 7 | 1.000 | 0.708 | 0.000 |
| Before | 0.70 | 22 | 11 | 2,521 | 2 | 0.667 | 0.917 | 0.0043 |
| After | 0.70 | 17 | 0 | 2,532 | 7 | 1.000 | 0.708 | 0.000 |

The new cap removes all different-actor pairs from the >=0.70 and >=0.90 predictions in this synthetic set, while reducing recall. At the 0.90 cutoff, the missed same-actor pairs rose from 4 to 7. The same seven pairs are below 0.70 after the change because the single-pillar cap is 0.65.

## Per-scenario results

Counts at a threshold are counts of labelled scenario pairs with confidence at or above that threshold. Means are rounded to three decimals.

| Scenario | Pairs | Mean before | Mean after | >=0.90 before | >=0.90 after | >=0.70 before | >=0.70 after |
|---|---:|---:|---:|---:|---:|---:|---:|
| copycat_style | 3 | 0.297 | 0.297 | 0 | 0 | 0 | 0 |
| infra_only | 3 | 0.992 | 0.992 | 3 | 3 | 3 | 3 |
| infra_restyled | 3 | 0.933 | 0.756 | 3 | 1 | 3 | 1 |
| multi_signal | 2 | 1.000 | 1.000 | 2 | 2 | 2 | 2 |
| pgp_restyled | 3 | 0.969 | 0.869 | 3 | 2 | 3 | 2 |
| pgp_reuse | 3 | 0.995 | 0.995 | 3 | 3 | 3 | 3 |
| random | 20 | 0.279 | 0.254 | 0 | 0 | 1 | 0 |
| shared_hosting | 3 | 0.364 | 0.381 | 0 | 0 | 0 | 0 |
| similar_handle | 3 | 0.350 | 0.350 | 0 | 0 | 0 | 0 |
| style_only | 4 | 0.675 | 0.610 | 0 | 0 | 2 | 0 |
| wallet_restyled | 3 | 0.967 | 0.967 | 3 | 3 | 3 | 3 |
| wallet_reuse | 3 | 0.996 | 0.996 | 3 | 3 | 3 | 3 |

## Missed same-actor pairs after the change

| Pair | Scenario | Identity | Infrastructure | Stylometry | Confidence |
|---|---|---:|---:|---:|---:|
| P019–P020 | style_only | 0.000 | 0.000 | 0.856 | 0.650 |
| P021–P022 | style_only | 0.000 | 0.000 | 0.927 | 0.650 |
| P023–P024 | style_only | 0.000 | 0.000 | 0.738 | 0.633 |
| P025–P026 | style_only | 0.000 | 0.000 | 0.630 | 0.508 |
| P057–P058 | pgp_restyled | 0.900 | 0.000 | 0.214 | 0.650 |
| P067–P068 | infra_restyled | 0.000 | 0.970 | 0.212 | 0.650 |
| P069–P070 | infra_restyled | 0.000 | 0.970 | 0.208 | 0.650 |

## False-positive leaders

Before, the top false positive was `P045–P054` at 0.865; the remaining top scores were 0.854, 0.844, 0.802, 0.789, 0.786, 0.762, 0.751, 0.724, and 0.716. After, the top ten false positives are all capped at 0.650; the updated list is in the `highest_scoring_false_positives` field in `audit/accuracy_results.json`.

## Test run

`audit/.venv313/bin/python -m pytest -p no:cacheprovider tests dashboard/test_theme.py -q` completed with **69 passed**. The 69 are 61 pre-existing tests under `tests/`, four new fusion-rule tests, and four dashboard theme tests. The dashboard implementation change was limited to the requested lead badge text/color/graph tier handling.

Existing test expectations updated for the intentional tier addition:

- `tests/test_confidence_tier.py::test_compare_and_candidates_include_tier` now allows `lead` and asserts the API’s `single_signal` and `raw_confidence` fields.
- `tests/test_explain.py::test_tier_hedge_uses_corroboration_and_three_decimal_confidence` now expects an uncorroborated result at 0.65 to be labeled `lead`.
- `dashboard/test_theme.py::test_tier_badges_have_words_and_high_contrast_distinct_colors` now checks four distinct colors, including `lead`.

Full stdout from the accuracy runs is retained in `audit/round1_before.log` and `audit/round1_after.log`; summary JSON is in `audit/accuracy_results.json`.
