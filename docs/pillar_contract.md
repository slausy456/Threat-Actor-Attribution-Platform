# Pillar contract

Every pillar exposes exactly one function:

```python
def compare(a: Persona, b: Persona) -> SignalResult
```

| Pillar | File | Looks at |
|---|---|---|
| Identity graph | `backend/app/services/identity_graph/matcher.py` | handle, PGP key, wallet |
| Stylometry | `backend/app/services/stylometry/matcher.py` | `Persona.texts` |
| Infrastructure | `backend/app/services/infrastructure_scan/matcher.py` | cert hash, favicon hash, server banner |

## Rules (enforced by `tests/test_pillar_contract.py`)
1. Returns a `SignalResult`: `score` in [0, 1] and `evidence` as a list of short readable strings.
2. Symmetric: `compare(a, b)` and `compare(b, a)` give the same score.
3. Pure: no database, no network, no mutation of inputs. (Neo4j or caching goes *behind* this function later.)
4. Evidence explains the score ("shared PGP key PGP-SYN-...", "banner is very common, weak signal"). The LLM explanation layer reads this.
5. Own your folder. Don't edit another pillar's file or `entities.py` without telling the team.

## Workflow
1. Implement `compare` in your file.
2. `python -m pytest tests -q` — your pillar's contract tests stop skipping and must pass.
3. `python scripts/evaluate_pillars.py` — check your column against the expected behaviour below.

## Expected behaviour (what "good" looks like)
| Scenario | Same actor? | identity | infra | style |
|---|---|---|---|---|
| pgp_reuse / wallet_reuse | yes | high | low | high |
| infra_only | yes | low | high | high |
| style_only | yes | low | low | high |
| multi_signal | yes | high | high | high |
| shared_hosting | no | low | **must stay low** | low |
| copycat_style | no | low | low | **must stay low** |
| similar_handle | no | **must stay low** | low | low |
| random | no | low | low | low |

Honest note: synthetic style text is easy, so don't over-trust a stylometry score
of 1.0 here. The real test is VeriDark later.

## Fusion
`fusion/pipeline.py: score_pair(a, b)` calls all three and fuses with
`fusion/scorer.py`. Weights are a starting guess (0.35 / 0.35 / 0.30). Tuning them
against `evaluate_pillars.py` is the fusion owner's job once pillars exist.
