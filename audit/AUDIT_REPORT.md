# Repository audit report

Audit date: 2026-10-21. Scope: local repository inspection and local-only execution. No live scanning, Tor access, or crawling was performed. No existing repository file was modified; artifacts from this audit are in `audit/`.

## 1. How the system works

`data/synthetic/personas.json` is loaded into Pydantic persona records by `backend/app/data_loader.py:12-15`. `backend/app/main.py:7-16` creates FastAPI and an in-memory `GraphStore`; `backend/app/services/storage/graph_store.py:32-60` creates persona and identifier nodes in NetworkX. Exact PGP, wallet, certificate, favicon, and server-banner values become identifier nodes. Handle values are deliberately left out of this graph.

For a comparison, `GraphStore.compare` calls the three pure matchers through `score_pair` (`backend/app/services/storage/graph_store.py:83-94`; `backend/app/services/fusion/pipeline.py:9-24`). Those matchers compare fields already present in the persona records. Their output scores and evidence are combined by the logistic formula in `backend/app/services/fusion/scorer.py:66-105`, then an optional explanation is added. The runtime store does not load the answer key.

The Streamlit app (`dashboard/app.py`) uses either the local API or an in-process `GraphStore` via `dashboard/client.py:88-150`. It presents search, candidate comparisons, a profile, a graph of the selected persona's top candidates, and CSV/JSON candidate downloads. The dashboard’s date range filters persona `first_seen`/`last_seen`; it is not a post-level timeline chart.

### Synthetic data snapshot

The existing dataset was present, so the generator was not run. JSON inspection found 72 personas, 48 actors, 53 deliberately labelled scenario pairs, and 432 posts. Identifier counts are **occurrences / unique values**: handles 72/64, PGP keys 72/64, wallets 72/64, certificate hashes 66/58, favicon hashes 66/58, server banners 56/42. The four sources are `market_alpha` (22 personas), `market_beta` (20), `market_gamma` (13), and `forum_delta` (17). Post dates range from `2024-01-06T00:00:00` through `2025-02-07T00:00:00`.

Three sample personas (identifiers abbreviated to avoid reproducing synthetic values in full):

| ID | Marketplace | Handle | Seen interval |
|---|---|---|---|
| P001 | market_gamma | ghost_hub | 2024-09-13 to 2025-01-10 |
| P002 | market_alpha | onyx_wolf63 | 2024-01-28 to 2024-05-26 |
| P003 | market_beta | nova_labs | 2024-04-01 to 2024-07-22 |

Three sample synthetic posts from P001 (verbatim):

1. `2024-12-30` — “Hello and welcome. stock refreshed todya for font collections. ask before you buy. order whenever ready.”
2. `2024-10-03` — “Hello and welcome. new batch of font collections just arrived. trusted since day one. order whenever ready.”
3. `2024-11-29` — “Hello and welcome. all design templates are tested before dispatch. trusted since day one. order whenever ready.”

The answer key is `data/synthetic/ground_truth.json`. It stores 48 actor records (each actor’s persona IDs) and 53 labelled persona pairs with `same_actor` and a `scenario` field. The data README describes it as fully fake, with deterministic generated handles, identifiers, and benign listing text.

### Repository map (2–3 levels)

```text
backend/
  app/main.py                         API entry point
  app/routers/api.py                  endpoint definitions
  app/data_loader.py                  synthetic data loading
  app/models/entities.py              Persona and signal data models
  app/services/{fusion,identity_graph,infrastructure_scan,stylometry,llm_explain,storage}/
dashboard/
  app.py                              Streamlit entry point
  client.py                           API/demo fallback, search, graph, exports
scripts/
  generate_synthetic_data.py
  train_fusion.py
  evaluate_pillars.py
  evaluate_retrieval.py
  evaluate_stylometry_real.py
tests/                                pytest modules
  test_api.py, test_fusion.py, test_pillar_contract.py, ...
data/
  synthetic/personas.json
  synthetic/ground_truth.json
  raw/, processed/, veridark/         empty except .gitkeep
reddit_open_split/                    bundled split directories; beyond this audit's synthetic runtime path
docker/docker-compose.yml
README.md, requirements.txt, backend/requirements.txt, dashboard/requirements.txt
```

Entrypoints: API `backend/app/main.py` (`uvicorn app.main:app` from `backend/`); dashboard `dashboard/app.py` (`python -m streamlit run dashboard/app.py`); generator and evaluations in `scripts/`. Dependency manifests: root, `backend/`, and `dashboard/` requirements files. README states Python 3.11+ (`README.md:58-68`); the interpreter actually used here was Python 3.14.8. Python 3.13.15 was also present but had the same missing packages. No `.python-version`, `pyproject.toml`, or lock file was found.

## 2. What runs and what fails

### Setup and tests

- A fresh virtual environment was created at `audit/.venv/`. Installing both `backend/requirements.txt` and root `requirements.txt` failed because the environment could not resolve `pypi.org`. Exact terminal error in `audit/install.log`: `NameResolutionError("HTTPSConnection(host='pypi.org', port=443): Failed to resolve 'pypi.org' ([Errno -2] Name or service not known)")`; pip ended with `ERROR: Could not find a version that satisfies the requirement fastapi>=0.110 (from versions: none)` and `ERROR: No matching distribution found for fastapi>=0.110`. No version conflict was observed; installation could not reach package metadata.
- `python -m pytest tests -q` was run. Result: **7 collection errors; 0 tests reached execution**, so pass/fail/skip counts are not available. `audit/pytest.log` contains full tracebacks.
  - `tests/test_api.py`, `test_confidence_tier.py`, `test_explain.py`, `test_fusion.py`, `test_pillar_contract.py`, `test_stylometry_real.py`: `ModuleNotFoundError: No module named 'sklearn'`.
  - `tests/test_dashboard_client.py`: `ModuleNotFoundError: No module named 'plotly'`.
- The system interpreter has FastAPI, Pydantic, pytest, NetworkX, NumPy, pandas, and httpx, but not scikit-learn, Plotly, or Streamlit. The new venv has no packages because installation failed.

### API

Uvicorn was started locally from `backend/` on `127.0.0.1:8765`. It exited before listening while importing `backend/app/services/stylometry/matcher.py:21`: `ModuleNotFoundError: No module named 'sklearn'`. Curl was attempted for health, list, detail, compare, candidates, and each export format. Every curl got `curl: (7) Failed to connect to 127.0.0.1:8765 after 0 ms: Could not connect to server`. There are no real HTTP responses to show. `audit/api_samples/*.json` records the failed attempt explicitly as `http_response_received: false`; companion `.curl_error` files contain curl’s exact error. Export samples are therefore not verified or produced.

### Dashboard and screenshots

`python -m streamlit run dashboard/app.py --server.headless true` failed immediately: `/usr/bin/python: No module named streamlit` (`audit/streamlit.log`). Although Playwright and browsers are installed, there was no running dashboard to screenshot. Date filtering, graph rendering, and exported files could not be exercised; no screenshots or export files were produced.

Code inspection identifies these views and controls (rendering was not verified):

| View/control | What the code shows | Drawing code |
|---|---|---|
| Sidebar observed date range | `st.date_input`, using min/max first/last seen values | `dashboard/app.py:72-83` |
| Search | Persona ID/handle/identifier text input, result count, selector, open button, result table | `dashboard/app.py:111-145`; matching in `dashboard/client.py:215-225` |
| Candidate Matches | Top 25 candidates table with confidence and three pillar columns; candidate selector and Compare button; explanation and evidence expanders | `dashboard/app.py:169-228` |
| Actor Profile | Marketplace, handle, observed dates, identifier table, expandable text samples, exact-identifier linked-persona table | `dashboard/app.py:230-271` |
| Graph View | Selected persona linked to up to 12 candidate nodes; tier-colored edges and strongest-signal labels; Plotly graph | `dashboard/app.py:274-282`; graph construction in `dashboard/client.py:276-377` |
| Export | Prepare/download candidate CSV or JSON | `dashboard/app.py:284-318`; payload logic in `dashboard/client.py:380-450` |

There is no separate timeline chart or dedicated confidence chart. Confidence is a candidate table value/badge and comparison text; graph tiers are another visual encoding. The date control filters persona observation intervals by overlap, not individual post dates. The dashboard has no report export button even though the API has a Markdown report format.

## 3. Real example outputs and comparison trace

Three pairs are present in the synthetic ground truth and suitable for exercising the three requested cases:

| Case | Pair | Ground-truth scenario | Answer key |
|---|---|---|---|
| Same actor | `P027`–`P028` | `multi_signal` | same actor |
| Different actors | `P031`–`P032` | `shared_hosting` | different actors |
| Different actors with copied style | `P037`–`P038` | `copycat_style` | different actors |

**Observed response for each pair:** not verified. The `/compare` request was attempted, but the server could not start due to the missing `sklearn` module. Exact curl error: `curl: (7) Failed to connect to 127.0.0.1:8765 after 0 ms: Could not connect to server`. See `audit/api_samples/compare.json` and `audit/api_samples/compare.curl_error`. Consequently, no actual per-pillar score, fused confidence, tier, or explanation can honestly be reported for these three pairs.

The scoring code path and constants (code inspection, not runtime values):

- Identity graph: shared PGP key contributes `0.90`, wallet `0.85`, identical handle `0.20`; similar handles use `SequenceMatcher`, only at ratio `>=0.88`, with score capped at `0.15` (`backend/app/services/identity_graph/matcher.py:26-34,42-79`). Multiple identity evidence scores combine as noisy-OR: `1 - ∏(1 - sᵢ)`.
- Infrastructure: shared certificate hash `0.90`, favicon hash `0.70`, uncommon banner `0.40`, common nginx/Apache banner `0.05`; multiple evidence items use the same noisy-OR formula, capped at `0.99` (`backend/app/services/infrastructure_scan/matcher.py:23-60`).
- Stylometry: `0.7 × character 3–5-gram TF-IDF cosine similarity + 0.3 × nine-feature style-habit similarity` (`backend/app/services/stylometry/matcher.py:41-77,88-105`). Actual scores for the selected pairs were not verified.
- Fusion loads `backend/app/services/fusion/weights.json` (values: intercept `-2.946513511852086`; identity `5.435351019529443`; infrastructure `4.459861983495649`; stylometry `4.729835109575675`). For pillar scores `I, N, S`, runtime computes `z = -2.946513511852086 + 5.435351019529443·I + 4.459861983495649·N + 4.729835109575675·S`, then confidence `1/(1+exp(-z))`, rounded to 3 decimals (`backend/app/services/fusion/scorer.py:45-63,74-105`). The `oof_decision_threshold` value `0.23307732774417655` present in the weights file is not loaded into the runtime weights dict. Tiers are `strong >= 0.90`, `moderate >= 0.70 and <0.90`, otherwise `weak` (`scorer.py:29-42`).

Plain-language expectations are not asserted as outputs: the multi-signal case is designed to share identity/infrastructure values; shared-hosting is designed to share a generic banner; copycat-style is designed to share catchphrases. Their real measured results could not be verified in this environment.

## 4. Accuracy numbers and calibration table

**Not verified.** Scoring every pair requires importing the stylometry module, which fails on missing `sklearn`. No accuracy values are fabricated. `audit/accuracy_check.py` is the requested standalone exhaustive evaluator: it scores all `72 choose 2 = 2,556` persona pairs, uses actor membership only after scoring to create evaluation labels, calculates precision/recall/FPR at the Strong (`0.90`) and Moderate (`0.70`) cutoffs, bins predicted confidence in 0.1 steps, and lists the 10 highest-scoring false positives. Running it here produced `ModuleNotFoundError: No module named 'sklearn'` (`audit/accuracy_run.log`); no `accuracy_results.json` was generated.

The dataset contains 72 personas and 48 actors. The actor table implies 24 same-actor persona pairs and 2,532 different-actor pairs among all 2,556 possible combinations. These are counts from the synthetic answer key, not model accuracy results.

Calibration table: not available; every bin’s score count and same-actor fraction is **not verified** because pair scores could not be calculated.

## 5. Weaknesses and risks

### Data and pillars

- `infrastructure_scan` does not scan. It compares already-populated `cert_hash`, `favicon_hash`, and `server_banner` identifier values (`backend/app/services/infrastructure_scan/matcher.py:29-60`). There is no socket, DNS, HTTP, TLS, or OnionScan call in this code path. It is a deterministic matcher over dataset fields.
- The NetworkX graph is an exact-identifier bipartite graph. It skips handles but adds other identifier types (`backend/app/services/storage/graph_store.py:38-60`). Handle equality/lookalikes are scored pairwise separately. The displayed profile links are also exact shared `(type,value)` matches (`dashboard/client.py:239-265`). The graph’s weights are stored but are not used in pair scoring.
- Stylometry is not a pretrained neural model: it uses per-comparison character TF-IDF n-grams and hand-built sentence/word length, casing, digit, punctuation, exclamation, ellipsis, and quote ratios. It examines both stylistic habits and shared lexical content. Because 70% is char n-gram similarity, repeated topic or phrases can raise the score; this is not a validated separation of author style from topic. The requested same-persona/two posts, same-topic/different-persona, and different-topic post test was **not verified** because scikit-learn is missing. The README’s `sentence-transformers` description (`README.md:43-48,58-62`) does not match the implementation. No external model download is needed by this implementation, but scikit-learn is a required runtime dependency.

### Fusion checklist

| Property | Yes/No | Evidence |
|---|---|---|
| Calibrated probability | **No evidence of calibration** | Logistic transform produces a 0–1 number, but no calibration method or independent calibration set is used in runtime (`scorer.py:74-99`). Training shifts the model intercept to a selected synthetic threshold (`scripts/train_fusion.py:44-70,95-122`); a sigmoid score is not by itself proof of probability calibration. |
| Conflicting evidence handled | **No** | Scores are added with positive learned coefficients; no contradiction penalty or conflict rule (`scorer.py:77-95`). |
| Time decay | **No** | Dates are used for persona listing/filtering, not comparison (`graph_store.py:65-81`; `pipeline.py:9-24`). |
| Source reliability | **No** | Marketplace/source identity does not affect a pillar or fusion weight. |
| Correlated signals | **No** | The logistic sum treats feature contributions as additive; no correlation/conditional dependence correction is applied at runtime (`scorer.py:77-83`). |
| Insufficient-evidence state | **No** | Each comparison returns a numeric confidence and one of three tiers; no evidence-count/quality gate is present (`scorer.py:36-42,97-105`). |

The weights are trained from synthetic labeled pairs (`scripts/train_fusion.py:25-41`) and then committed in `weights.json`. This is a trained linear classifier followed by a sigmoid, not an evaluated real-data confidence calibration. Fixed tiers do not change the score and README itself warns they do not generalise (`README.md:112-120`).

### LLM explanation

With no key, code chooses `_template` (`backend/app/services/llm_explain/explainer.py:124-128,165-172`). The template shape is: `Confidence is {score} ({tier} tier); {hedge}. {per-pillar evidence summary}. Treat this as a lead for human review, not proof of attribution.` A concrete rendered response requires a comparison result, which could not be generated here. If configured, LLM output is constrained to one 20–700 character sentence, blocks certain definitive attribution phrases, and rejects identifiers absent from evidence (`explainer.py:110-121,137-161`). This is a useful partial validation, but it does not prove that non-identifier factual claims are entailed by the supplied evidence.

### Ground-truth leakage check

The runtime score path (`fusion/pipeline.py`, its matchers, scorer, and `GraphStore`) does not read actor IDs, `same_actor`, scenario labels, or `ground_truth.json`. `GraphStore` loads only personas (`graph_store.py:9,29-34`). The stored fusion weights were trained from ground-truth labels, so training is supervised; the runtime does not read those labels directly. Reads/evaluation of ground truth occur in:

- `backend/app/data_loader.py:18-20` (`load_ground_truth` implementation).
- `scripts/train_fusion.py:15,25-40` (supervised feature/label construction).
- `scripts/evaluate_pillars.py:17,23-24,40-52` and `scripts/evaluate_retrieval.py:14,57-73` (evaluation).
- `scripts/check_acceptance.py:182-183` (acceptance evaluation; it also scans source for suspicious patterns at lines 118 onward).
- Tests: `tests/test_synthetic_data.py:9-13`, `tests/test_fusion.py:1-6`, `tests/test_pillar_contract.py:8-15`, and `tests/test_explain.py:3,118`.
- The audit-only evaluator reads labels after calling `score_pair` to compute metrics (`audit/accuracy_check.py`).
- `scripts/generate_synthetic_data.py` writes the ground-truth file (`:14-16,340`); it is not a runtime scoring read.

The training and claimed retrieval assessment use the same synthetic dataset family. Results should not be presented as generalization to real actors or real marketplaces.

## 6. README vs reality

| README claim | Status | Evidence |
|---|---|---|
| Six listed API endpoint families exist | PARTLY | Routes are defined in `backend/app/routers/api.py:59-174`; live requests could not run due missing sklearn. |
| Strong/Moderate/Weak thresholds are 0.90/0.70 | TRUE (code) | `scorer.py:29-42`; not an empirically verified deployment threshold. |
| Dashboard can run standalone with in-process scoring | PARTLY | Fallback path exists (`dashboard/client.py:88-150`), but requires the same backend scoring dependencies; Streamlit and sklearn are absent here. |
| API connection failures fall back to demo mode | PARTLY | Request exceptions return `None`, then helpers use `_demo_store` (`client.py:132-167`); fallback itself cannot score without sklearn. |
| No model download or GPU needed | PARTLY | Current implementation does not load a pretrained model; TF-IDF is local. README’s sentence-transformers claim is stale and runtime still needs sklearn. |
| CSV/JSON/report export | PARTLY | API code branches for all three (`api.py:110-174`); dashboard offers CSV and JSON only (`dashboard/app.py:284-315`). Not runtime-verified. |
| Tests can be run with pytest | PARTLY | Tests are present, but this environment’s requested command stops during collection with seven missing-dependency errors. |

## 7. Problem statement coverage

| Requirement | Status | Reason |
|---|---|---|
| (1) Find hidden-service misconfigurations and match clearnet infrastructure | MISSING | No scanner or network collection; only precomputed certificate/favicon/banner field comparison. |
| (2) Cross-marketplace graph of handles, PGP, wallets, trust links | PARTIAL | Synthetic marketplace personas and exact PGP/wallet matching exist; handles are omitted from stored graph, trust links and real marketplace ingestion are absent. |
| (3) Stylometric and behavioural persona linking | PARTIAL | Text similarity and simple style features exist; no behavioural features or trained authorship model. |
| (4) Autonomous collection | MISSING | No collection/crawling workflow; README explicitly scopes live collection out. |
| (5) Store profile, identifiers, infra indicators, linkages, confidence, category, scan date, source | PARTIAL | Persona text, identifiers, marketplace, dates, and computed link scores exist; no category, last-scan timestamp, scan lifecycle, or persistent DB. |
| (6) GUI with timeline queries | PARTIAL | Dashboard has observed-date range overlap filtering; no timeline query language or timeline visualization. |
| (7) Export CSV/JSON/report | PARTIAL | API source implements three formats; dashboard has two. None could be exercised in this environment. |
| (8) Calibrated, explainable confidence | PARTIAL | Per-pillar breakdown/evidence and template explanation exist. Probability calibration and conflict/uncertainty handling are absent. |

## 8. Top 10 recommended fixes, ranked by impact

1. Make setup reproducible: select a supported Python version, pin/test dependency ranges, and add CI that installs the root and backend requirements before tests.
2. Add an independent, correctly split evaluation set (and real authorized research data if available) before presenting confidence as attribution probability.
3. Calibrate confidence on held-out data and report calibration metrics; keep decision thresholds separate from probability calibration.
4. Add an explicit insufficient-evidence outcome and handle contradictory signals; test each case with ground-truth scenarios.
5. Separate lexical/topic overlap from author-style features and validate same-author/different-topic and different-author/same-topic behavior.
6. Replace the infrastructure matcher’s misleading “scan” framing with explicit provenance/field semantics; only add active scanning under an authorized, separately reviewed scope.
7. Add source quality/reliability and time-aware evidence handling, with tests demonstrating how those affect confidence.
8. Add persistence and complete profile fields (category, source provenance, last scan/observation date, linkage history) if required by the problem statement.
9. Make dashboard exports and date filters consistent with API capabilities; add a genuine post/persona timeline visualization and test all three export formats.
10. Strengthen explanation checks so all generated factual statements are grounded in supplied evidence, and cover both LLM and no-key fallback paths with executable tests.

## Audit artifacts

- Setup and test logs: `audit/install.log`, `audit/pytest.log`
- Uvicorn and Streamlit logs: `audit/uvicorn.log`, `audit/streamlit.log`
- Curl attempts: `audit/api_samples/`
- Exhaustive pair evaluator: `audit/accuracy_check.py`; failed run log: `audit/accuracy_run.log`
- Screenshot and export directories are empty because the dashboard did not start and API exports were unavailable.
