# Confidence Tiers

The API returns the fused confidence, its uncapped `raw_confidence`, and whether
the comparison is `single_signal`. Two or more pillar scores must each reach
`MIN_PILLAR_SCORE` (default `0.30`, configured in
`backend/app/services/fusion/config.json`) for a result to be corroborated.
Results with fewer than two qualifying pillars are capped by
`SINGLE_SIGNAL_CAP` (default `0.65`) and receive the `lead` tier. These values
are not calibrated probabilities and are intended for human triage.

| Tier | Fused confidence | Interpretation |
|---|---:|---|
| Strong | >= 0.90, corroborated | Higher-priority lead; evidence is still not conclusive. |
| Moderate | >= 0.70 and < 0.90, corroborated | A lead with mixed or incomplete evidence. |
| Weak | < 0.70, corroborated | Limited support; do not treat as proof of attribution. |
| Lead | Any confidence, fewer than 2 qualifying pillars | Uncorroborated result, capped at the configured single-signal limit. |

The cutoffs come from `scripts/evaluate_retrieval.py` run on the synthetic
dataset. At the strong cutoff, the report observed zero false positives among
2,556 persona pairs. The cutoff was selected on this dataset and is not proven
to generalise to research or operational data. Single-signal capping changes
the reported `confidence`; `raw_confidence` preserves the pre-cap score.
