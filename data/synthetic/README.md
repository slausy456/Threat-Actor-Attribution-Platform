# Synthetic dataset

Fully fake data used to build and test every pillar with a **known answer key**.
Nothing here comes from real dark web sources.

- `personas.json` — 72 personas (one identity on one marketplace each)
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
| pgp_restyled | yes | shared PGP key, but the actor **deliberately changed writing style** |
| wallet_restyled | yes | shared wallet, writing style changed |
| infra_restyled | yes | shared cert/favicon, writing style changed |
| shared_hosting | no | same generic server banner — trap for infra pillar |
| copycat_style | no | copied catchphrases — trap for stylometry pillar |
| similar_handle | no | look-alike handles — trap for identity pillar |
| random | no | unrelated personas (baseline) |

A good fusion score should be high for every "yes" row and low for every "no" row.

The three `*_restyled` scenarios exist because in the first five same-actor scenarios the
two personas always share a writing style, which makes stylometry look nearly sufficient on
its own. Real actors can change how they write. In the restyled scenarios stylometry is
blind and the identity or infrastructure pillar must carry the match. They were appended to
the generator last, so the original 54 personas and 44 pairs are byte-identical to the
earlier version of the dataset.
Each pillar alone should fail on at least one scenario — that's the whole argument
for fusing them.
