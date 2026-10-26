# Fusion rules: rounds 0–2

The accuracy evaluator scores all 2,556 possible pairs among 72 personas. There are 24 same-actor pairs and 2,532 different-actor pairs. The labelled scenarios in `ground_truth.json` are a subset; the metrics below use all possible pairs. “Found” means true positives at the stated confidence cutoff.

## Overall results

| Round | >= 0.90 found / 24 | >= 0.90 false positives | >= 0.70 found / 24 | >= 0.70 false positives |
|---|---:|---:|---:|---:|
| 0: original scorer | 20 | 0 | 22 | 11 |
| 1: single-signal cap | 17 | 0 | 17 | 0 |
| 2: hard-identifier exception | 20 | 0 | 20 | 0 |

Round 0’s commonly cited “20/24 found, 11 false positives” combines the 0.90 true-positive count with the 0.70 false-positive count. At a consistent cutoff, round 0 had 20/24 and 0 false positives at 0.90; at 0.70 it had 22/24 and 11 false positives. Round 2 restores three of round 1’s missed high-confidence matches without restoring any >=0.70 false positives.

## Per-scenario comparison

Counts are from the labelled scenario pairs. Means and counts for rounds 0 and 1 are retained from the round 1 audit; round 2 is the current `audit/accuracy_check.py` run.

| Scenario | Pairs | Mean confidence R0 / R1 / R2 | >=0.90 R0 / R1 / R2 | >=0.70 R0 / R1 / R2 |
|---|---:|---:|---:|---:|
| copycat_style | 3 | 0.297 / 0.297 / 0.297 | 0 / 0 / 0 | 0 / 0 / 0 |
| infra_only | 3 | 0.992 / 0.992 / 0.992 | 3 / 3 / 3 | 3 / 3 / 3 |
| infra_restyled | 3 | 0.933 / 0.756 / 0.933 | 3 / 1 / 3 | 3 / 1 / 3 |
| multi_signal | 2 | 1.000 / 1.000 / 1.000 | 2 / 2 / 2 | 2 / 2 / 2 |
| pgp_restyled | 3 | 0.969 / 0.869 / 0.969 | 3 / 2 / 3 | 3 / 2 / 3 |
| pgp_reuse | 3 | 0.995 / 0.995 / 0.995 | 3 / 3 / 3 | 3 / 3 / 3 |
| random | 20 | 0.279 / 0.254 / 0.254 | 0 / 0 / 0 | 1 / 0 / 0 |
| shared_hosting | 3 | 0.364 / 0.381 / 0.381 | 0 / 0 / 0 | 0 / 0 / 0 |
| similar_handle | 3 | 0.350 / 0.350 / 0.350 | 0 / 0 / 0 | 0 / 0 / 0 |
| style_only | 4 | 0.675 / 0.610 / 0.610 | 0 / 0 / 0 | 2 / 0 / 0 |
| wallet_restyled | 3 | 0.967 / 0.967 / 0.967 | 3 / 3 / 3 | 3 / 3 / 3 |
| wallet_reuse | 3 | 0.996 / 0.996 / 0.996 | 3 / 3 / 3 | 3 / 3 / 3 |

## Round 1 missed pairs and round 2 tier changes

| Pair | Scenario | Round 1 | Round 2 | Reason |
|---|---|---|---|---|
| P019–P020 | style_only | lead, 0.650 | lead, 0.650 | Stylometry-only; no hard identifier evidence. |
| P021–P022 | style_only | lead, 0.650 | lead, 0.650 | Stylometry-only; no hard identifier evidence. |
| P023–P024 | style_only | lead, 0.633 | lead, 0.633 | Stylometry-only; no hard identifier evidence. |
| P025–P026 | style_only | lead, 0.508 | lead, 0.508 | Stylometry-only; no hard identifier evidence. |
| P057–P058 | pgp_restyled | lead, 0.650 | strong, 0.951 | Exact shared PGP key; identity score 0.900 meets `HARD_IDENTIFIER_MIN` (0.85), so it bypasses the cap. |
| P067–P068 | infra_restyled | lead, 0.650 | strong, 0.915 | Exact shared certificate hash; infrastructure score 0.970 meets the minimum, so it bypasses the cap. |
| P069–P070 | infra_restyled | lead, 0.650 | strong, 0.914 | Exact shared certificate hash; infrastructure score 0.970 meets the minimum, so it bypasses the cap. |

Only the three exact hard-identifier matches change tier, from `lead` to `strong`. All four style-only pairs remain `lead` because style evidence is never self-corroborating.

## Verification

- `audit/.venv313/bin/python audit/accuracy_check.py`: 2,556 pairs; at >=0.90, 20 TP / 0 FP / 4 FN; at >=0.70, 20 TP / 0 FP / 4 FN.
- `audit/.venv313/bin/python -m pytest -p no:cacheprovider tests -q`: **72 passed**.
