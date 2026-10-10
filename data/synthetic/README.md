# Synthetic dataset

Fully fake data used to build and test every pillar with a **known answer key**.
Nothing here comes from real dark web sources.

- `personas.json` — 54 personas (one identity on one marketplace each)
- `ground_truth.json` — `actors` (which personas are really the same actor) and
  labelled `pairs`, each tagged with a `scenario`

Regenerate (deterministic, seed 42 — everyone gets identical data):

    python scripts/generate_synthetic_data.py

## Scenarios
| scenario | same actor? | what it tests |
|---|---|---|
| pgp_reuse | yes | shared PGP key only |
| wallet_reuse | yes | shared wallet only |
| infra_only | yes | shared cert/favicon, no shared identifiers |
| style_only | yes | **nothing shared except writing style** (hardest) |
| multi_signal | yes | PGP + wallet + infra all shared |
| shared_hosting | no | same generic server banner — trap for infra pillar |
| copycat_style | no | copied catchphrases — trap for stylometry pillar |
| similar_handle | no | look-alike handles — trap for identity pillar |
| random | no | unrelated personas (baseline) |

A good fusion score should be high for every "yes" row and low for every "no" row.
Each pillar alone should fail on at least one scenario — that's the whole argument
for fusing them.
