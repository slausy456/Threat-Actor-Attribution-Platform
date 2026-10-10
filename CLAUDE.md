# Project context for Claude

Threat Actor Attribution Platform (SIH26151 prototype). One developer.
Goal: decide whether two personas (one identity on one marketplace) are the same
real-world actor by fusing three signals: identity graph, infrastructure, stylometry.

## Read first
- `docs/build_plan.md` — ordered checklist; find the first unchecked step and continue from there
- `docs/pillar_contract.md` — the one function every pillar must implement
- `docs/ethics_and_data_sources.md` — hard scope limits

## Current state
Steps 1-2 are done (data model, synthetic dataset, pillar stubs, tests, eval script).
Next: Step 3, implement the pillars in this order: identity_graph, infrastructure_scan, stylometry.

## Commands (run from repo root)
- Tests: `python -m pytest tests -q` (currently `12 passed, 9 skipped`; skips disappear as pillars are built)
- Evaluation table: `python scripts/evaluate_pillars.py`
- Acceptance checks: `python scripts/check_acceptance.py` (the objective test of whether a step is really done)
- Regenerate synthetic data: `python scripts/generate_synthetic_data.py` (seeded, deterministic)

## Rules
- Every pillar: `compare(a: Persona, b: Persona) -> SignalResult`; pure, symmetric, score in [0, 1], evidence as readable strings.
- Don't change `backend/app/models/entities.py` or pillar signatures without updating `docs/pillar_contract.md` and the tests.
- Never write code that scans, crawls or connects to live Tor services or real marketplaces. Datasets only (synthetic, or published research data such as VeriDark).
- Don't put personal names in repo files.
- Run the tests before every commit. Keep commits small, one step at a time.
- Outputs are leads for human review, not accusations; don't present scores as calibrated probabilities.

## Definition of done (every step)
A step is done only when `python -m pytest tests -q` passes AND `python scripts/check_acceptance.py`
shows no FAIL lines. When you report a step as finished, paste the UNEDITED output of both commands.
Never summarise a failing check as passing.

- Do not edit the protected files listed in `scripts/check_acceptance.py` (data, models, existing tests,
  the checker itself) to make a check pass. If one genuinely must change, stop and tell the user why first.
- Do not loosen thresholds in the checker. If a threshold looks unreasonable, say so and let the user decide.
- Pillar and fusion code under `backend/app/services/` must not read ground-truth labels, scenario names or
  persona ids. Anything that learns from labels (e.g. fitting fusion weights) lives in `scripts/` and saves
  its result to a JSON file that the service code loads.
- If you tune anything on the synthetic pairs, say so and report a held-out result as well.
- Call out limitations honestly instead of hiding them (synthetic data is easy; scores are not probabilities).
