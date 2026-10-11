# Build plan (single-developer edition)

Status legend: [x] done, [ ] to do. Work top to bottom; each step ends with a
check you can run. Don't skip ahead to dashboard/database work — they depend on
decisions made in steps 3-5.

## Definition of done (applies to every step)
1. `python -m pytest tests -q` passes (no failures; skips only for steps not started).
2. `python scripts/check_acceptance.py` shows no FAIL lines. It checks that protected files are unchanged,
   that service code does not cheat or touch Tor, that each pillar wins its scenarios and stays low on its
   trap, that fusion beats every single pillar, and that explanations are grounded in the evidence.
3. The raw output of both commands is pasted to the reviewer. Steps 7 to 10 are verified by running the
   thing (curl/TestClient output, a screenshot, the written report), not by this script.

## Done
- [x] Repo scaffold, docs (architecture, roadmap, ethics, gap analysis)
- [x] **Step 1 — Data layer:** `backend/app/models/entities.py`, synthetic dataset
      (`scripts/generate_synthetic_data.py` -> `data/synthetic/`), loader, 12 tests
- [x] **Step 2 — Pillar contract:** stub `matcher.py` in each pillar folder,
      `fusion/pipeline.py`, `tests/test_pillar_contract.py`, `scripts/evaluate_pillars.py`,
      `docs/pillar_contract.md`
- [x] **Step 5 — Explanation layer:** deterministic grounded fallback, optional timed LLM,
      evidence-validation tests
- [x] **Step 6 — Storage:** in-memory NetworkX persona/identifier graph and cached comparisons
- [x] **Step 7 — API:** FastAPI persona, compare, candidate, and CSV/JSON/Markdown export routes
- Check: `python -m pytest tests -q` -> `12 passed, 9 skipped`

---

## Step 3 — Implement the pillars (one at a time, in this order)

Contract for all: `compare(a: Persona, b: Persona) -> SignalResult`
(pure, symmetric, score 0-1, evidence = readable strings). Expected behaviour per
scenario is the table in `docs/pillar_contract.md`.

### 3a. Identity graph — `services/identity_graph/matcher.py`
- Exact PGP match -> strong (~0.90). Exact wallet match -> strong (~0.85).
- Handle similarity (e.g. `difflib.SequenceMatcher`) -> WEAK, capped around 0.15,
  and only when similarity is high. The `similar_handle` trap must stay low.
- Combine independent signals with noisy-OR: `score = 1 - prod(1 - s_i)`, so two
  matches reinforce each other without exceeding 1.
- Evidence strings, e.g. `"shared PGP key PGP-SYN-AB12..."`, `"no shared identifiers"`.
- Done when: contract tests for this pillar pass, and `evaluate_pillars.py` shows
  high for pgp_reuse / wallet_reuse / multi_signal and low for everything else.

### 3b. Infrastructure — `services/infrastructure_scan/matcher.py`
- Cert hash match -> strong (~0.90). Favicon hash match -> strong-ish (~0.70).
- Server banner match -> weak. A COMMON banner (`nginx/1.18.0 (Ubuntu)`,
  `Apache/2.4.41 (Ubuntu)`) should add ~0.05; a rare custom banner ~0.40.
  Keep a `COMMON_BANNERS` set in the module (or compute banner frequency from the
  dataset once, at import). The `shared_hosting` trap must stay low.
- Combine with noisy-OR as above. Dataset records only — NO live scanning.
- Done when: high for infra_only / multi_signal, low for shared_hosting.

### 3c. Stylometry — `services/stylometry/matcher.py`
- IMPORTANT: all synthetic texts share the same topic, so topic-focused embeddings
  (sentence-transformers) will barely separate personas. Start with
  **character n-gram TF-IDF + cosine** (scikit-learn; add to requirements) plus
  hand-built style features: end-of-sentence punctuation habit, lowercase ratio,
  average sentence length, misspelling patterns.
- Optionally add a sentence-transformers score and compare which works better —
  that comparison is a nice result for the report.
- Represent each persona as the mean of its text vectors, then cosine similarity;
  map to 0-1 (calibrate so same-actor ~0.8+, different ~0.3 or lower).
- `copycat_style` trap: copied catchphrases but different punctuation/typo habits.
  Document how your features handle it (or honestly that they only partly do).
- Done when: style_only pairs score high, copycat/random score clearly lower.

### Step 3 check
`python -m pytest tests -q` -> no skips, all pass.
`python scripts/evaluate_pillars.py` -> table matches the expected behaviour;
each pillar should be BLIND to at least one scenario (that justifies fusion).

---

## Step 4 — Fusion — `services/fusion/scorer.py` + `pipeline.py`
- KNOWN DESIGN ISSUE: the current weighted average (0.35/0.35/0.30) dilutes
  single strong signals. A pgp_reuse pair gives identity ~0.9, infra ~0, style
  ~0.8 -> fused ~0.55. Decide an approach and justify it with the eval table:
  noisy-OR across pillars, max-with-corroboration bonus, or logistic regression
  fitted on the labelled synthetic pairs. (Logistic regression gives learned,
  explainable weights — good for the report.)
- If you fit weights (logistic regression), do it in a script under `scripts/`, save the weights to a JSON
  file, and have `fusion/scorer.py` load that file. Service code must not read ground-truth labels.
- Add `scripts/evaluate_pillars.py` metrics: precision, recall, F1 at a chosen
  threshold (e.g. 0.5), overall and per scenario.
- Result to aim for: fusion beats every single pillar on overall F1 and fixes
  each pillar's blind spot, without being fooled by the traps.
- Add tests: fused score high for all same-actor scenarios, low for all negatives.

## Step 5 — Explanation layer — `services/llm_explain/`
- Input: dict from `score_pair` (fused confidence, per-pillar scores, evidence).
- Output: 2-4 sentence plain-language justification for an investigator, including
  uncertainty ("moderate confidence; based on writing style only").
- Provide a deterministic TEMPLATE-based fallback that works with no API key, then
  the LLM version behind the same function (`explain(result) -> str`).
- LLM prompt must forbid inventing facts not in the evidence list.
- Config via `.env` (see `.env.example`). Never commit API keys.

## Step 6 — Storage (keep it light)
- First: NetworkX in memory (build graph from personas; edges = shared identifiers,
  weighted by pillar scores). JSON/SQLite is enough for persistence.
- Neo4j + Postgres + Docker only AFTER steps 3-5 work. Keep the same function
  signatures so it's a contained swap.

## Step 7 — API — `backend/app/main.py` + `routers/`
- `GET  /personas`                 list personas
- `GET  /personas/{id}`            one persona
- `POST /compare {a, b}`           fused score + breakdown + explanation
- `GET  /personas/{id}/candidates?top=5`   best matches for a persona
- `GET  /export?format=csv|json`   results export
- Add API tests with FastAPI `TestClient`.

## Step 8 — Dashboard — `dashboard/app.py` (Streamlit)
- Tabs already scaffolded: Search, Actor Profile, Graph View, Export.
- Wire to the API; show confidence breakdown, evidence, explanation, graph view.
- Timeline query (filter by `first_seen` / `last_seen`) is in the original problem
  statement — include it.

## Step 9 — Real research data (stylometry validation)
- Check VeriDark access terms/licence. Only legal, published datasets
  (see `docs/ethics_and_data_sources.md`). NEVER crawl live Tor services.
- Write an adapter that converts VeriDark records into `Persona`/`TextSample`.
- Re-evaluate the stylometry pillar on it; report honestly that results differ
  from synthetic data.

## Step 10 — Report, presentation, patent prep
- Update `docs/roadmap.md` dates to the single-developer timeline.
- Report sections: problem, existing work + gaps, method, evaluation table
  (the main result), limitations, ethics, future work (Phase 2 live collection
  needs institutional authorisation).
- Limitations to state plainly: synthetic text is easy; confidence scores are
  not calibrated probabilities; attribution outputs are leads for human review.
- Pending deliverable never produced: PPT content — objectives slide, slide
  structure (problem -> existing landscape -> fusion gap -> architecture ->
  ethical scoping -> roadmap -> results), and a prompt for an AI deck tool
  (the earlier deck was made in Gamma). Ask for these in a new chat if needed.
- Patent: ask the teacher what a disclosure needs. The novelty claim is the
  fused, explainable, confidence-scored combination of the three signal types.
  Don't publish details publicly before that conversation.

---

## Working rules
- Small commits, one step at a time. Run `python -m pytest tests -q` before each.
- Don't change `entities.py` or the pillar function signatures without updating
  `docs/pillar_contract.md` and the tests.
- No live Tor/dark-web scanning or scraping in any code. Ever.
- No personal names in repo files.
