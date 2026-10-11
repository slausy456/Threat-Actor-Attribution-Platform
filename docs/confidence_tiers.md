# Confidence Tiers

The API adds a descriptive tier alongside the unchanged fused confidence score.
These values are not calibrated probabilities and are intended to help triage
leads for human review.

| Tier | Fused confidence | Interpretation |
|---|---:|---|
| Strong | >= 0.90 | Higher-priority lead; the evidence is still not conclusive. |
| Moderate | >= 0.70 and < 0.90 | A lead with mixed or incomplete evidence. |
| Weak | < 0.70 | Limited support; do not treat as proof of attribution. |

The cutoffs come from `scripts/evaluate_retrieval.py` run on the synthetic
dataset. At the strong cutoff, the report observed zero false positives among
2,556 persona pairs. The cutoff was selected on this dataset and is not proven
to generalise to research or operational data. The numeric confidence remains
unchanged; the tier is additive display metadata only.
