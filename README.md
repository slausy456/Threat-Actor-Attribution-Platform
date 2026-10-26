# Threat Actor Attribution Platform

**Problem Statement:** SIH26151 — Dark Web Threat Actor De-anonymization (NTRO / SIH 2026)
**Status:** Prototype in development (semester project — see Roadmap)

## What this is
A multi-signal, confidence-scored attribution framework that fuses three evidence
pillars — infrastructure fingerprinting, identity-graph correlation, and AI-based
stylometric/behavioural linkage — into one explainable pipeline, instead of treating
each signal in isolation the way most existing tools do.

## What this is NOT (scope boundary — read this first)
This prototype does **not** perform live scanning or crawling of real Tor hidden
services. All development, training, and demonstration for this semester's prototype
runs against **published, legal research datasets** (see `data/README.md` and
`docs/ethics_and_data_sources.md`). Live infrastructure scanning against real dark
web targets is explicitly scoped as **Phase 2 / future work**, requiring
institutional authorization — see `docs/roadmap.md`.

## Why this exists (the gap)
Existing tools each solve one pillar well (OnionScan for infrastructure leaks,
VendorLink/PGP-correlation papers for identity graphs, VeriDark-trained stylometry
models for authorship linkage) but none fuse all three into one pipeline with a
shared, calibrated confidence score. That integration — plus an explainable,
investigator-facing confidence layer — is this project's actual contribution.
See `docs/literature_gap_analysis.md` for the full breakdown.

## Objectives
1. Design and implement a fusion engine combining infrastructure fingerprinting,
   identity-graph correlation, and stylometric similarity into one calibrated
   confidence score.
2. Build and validate the system entirely on legal, published research datasets
   (VeriDark, published DNM correlation data).
3. Develop an explainable AI layer that generates plain-language reasoning for
   each attribution match, rather than a black-box score.
4. Deliver a queryable analytical dashboard (search, actor profile, graph
   exploration, timeline, confidence visualization) with CSV/JSON/report export.
5. Document a clear phased roadmap separating the legal-dataset-based semester
   prototype from future live-deployment work requiring institutional authorization.

## Repo layout
```
backend/        FastAPI service: ingestion, graph building, fusion scoring, API
  app/services/infrastructure_scan/   wraps OnionScan-style output (dataset-based)
   app/services/identity_graph/        PGP/handle/wallet correlation
  app/services/stylometry/            sentence-transformers embedding similarity
  app/services/fusion/                combines signals into one confidence score
  app/services/llm_explain/           generates plain-language reasoning per match
   app/services/storage/               in-memory NetworkX persona/identifier graph
dashboard/      Streamlit UI: search, actor profile, graph view, export
data/           raw/processed/veridark — see data/README.md before adding anything
docker/         docker-compose for Neo4j + Postgres + backend + dashboard
docs/           architecture, roadmap, ethics/data-sourcing, literature gap analysis
scripts/        setup and dev helper scripts
tests/          unit/integration tests
```

## Tech stack
- **Backend:** Python 3.11+, FastAPI
- **Storage:** in-memory NetworkX graph (database persistence is future work)
- **Stylometry:** sentence-transformers (embedding similarity)
- **Explanation layer:** optional Groq or OpenAI LLM with a grounded template fallback
- **Dashboard:** Streamlit
- **Infra:** Docker Compose

## Prerequisites
- Python 3.11+
- Git

## Quickstart
The current prototype uses the local synthetic dataset and in-memory NetworkX storage. No database, Docker service, or LLM key is required for the API.

```powershell
git clone <this-repo-url>
cd threat-actor-attribution
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`. Run Uvicorn from the `backend` directory so `app.main` resolves correctly. An LLM key is optional; without one, explanations use the deterministic template.

### Explanation layer

The API and dashboard load the repository-root `.env` file at startup without
overriding variables already set in the real environment. Copy `.env.example` to
`.env` and configure:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `groq` or `openai` |
| `LLM_API_KEY` | API key for the selected provider; never included in responses or logs |
| `LLM_MODEL` | Model name; defaults to the provider's configured default |

Check connectivity (one short request; no key is printed) from the repository
root:

```powershell
python scripts/check_llm.py
```

Each comparison includes a source label next to its explanation. **AI-generated
(`<model>`)** means the LLM response passed evidence validation. **Template
(`<reason>`)** means the deterministic fallback was used; the reason identifies
why an LLM explanation was unavailable or rejected. Both are qualitative
explanations for human review, not proof of attribution.

The default Groq model is `openai/gpt-oss-20b`; set `LLM_MODEL` to override it.
The dashboard generates explanations only when a pair is opened or when
**Explain top 5** is selected. The Overview scores pairs without LLM calls.
Explanations are cached by persona pair and model, calls run one at a time with
at least one second between requests, and each session allows 30 LLM calls by
default. If the provider rate-limits a request, the dashboard retries once,
then uses template explanations for 60 seconds.

### Dashboard

The dashboard runs standalone with the bundled synthetic dataset and in-process
scoring; a separate API server is optional. From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

When `ATTRIBUTION_API_URL` is unset, the sidebar identifies in-process demo
mode. To connect to the optional local API, set `ATTRIBUTION_API_URL` to its
loopback URL (for example, `http://127.0.0.1:8000`). Streamlit Community Cloud
can set the same key in App settings under Secrets; no API URL is needed for
standalone deployment. Requests use the API when reachable and fall back to
in-process scoring when it is unavailable. No model download or GPU is required.

The dashboard opens at `http://localhost:8501` by default. Its Overview,
Search, Compare, Timeline, Graph, and Export tabs use the active date filter.
Overview progressively scores pairs in batches and shows the top results; it
does not request LLM explanations. The sidebar displays the remaining
explanation-call budget for the current session.

For Streamlit Community Cloud, deploy this repository with `dashboard/app.py`
as the Main file path. Community Cloud installs runtime dependencies from the
root `requirements.txt`; leave `ATTRIBUTION_API_URL` unset to use standalone
demo mode. The dashboard only uses the bundled synthetic dataset in that mode.

The date-range control filters by the persona's `first_seen` and `last_seen`
fields.

Available endpoints: `GET /health`, `GET /personas`, `GET /personas/{id}`, `POST /compare`, `GET /personas/{id}/candidates`, and `GET /export?format=csv|json|report`. The `since` and `until` filters select personas whose observed date range overlaps the requested interval.

### Confidence tiers

API comparison and candidate results include a tier, `single_signal`, and the
uncapped `raw_confidence`. A result with fewer than two pillars at or above the
configured minimum is capped and labeled `lead`.

| Tier | Fused confidence |
|---|---:|
| Strong | >= 0.90 with corroboration |
| Moderate | >= 0.70 and < 0.90 with corroboration |
| Weak | < 0.70 with corroboration |
| Lead | Fewer than two pillars meet the configured minimum |

These cutoffs were assessed on the synthetic dataset and are not proven to generalise. See [docs/confidence_tiers.md](docs/confidence_tiers.md) for the evaluation caveat.

## Running tests
From the repo root:
```bash
pip install -r backend/requirements.txt
python scripts/generate_synthetic_data.py   # only needed if data/synthetic is missing
python -m pytest tests -q
```

## Data
See `data/README.md` before adding anything to `data/`. Only legal, published
research datasets are permitted — no live-scraped dark web data.

### VeriDark stylometry evaluation

For the optional real-data pair-verification evaluation, place locally obtained
VeriDark JSON files under `data/veridark/` with one file per pair and this
layout:

```text
data/veridark/
   train/<pair>.json
   val/<pair>.json
   test/<pair>.json
```

Each file must contain `{"id": "...", "pair": ["text1", "text2"], "same": true}`.
The evaluator reads only these three split directories; it ignores duplicate
folders such as `val+test/` and `train+val+test/`. Get the dataset only from its
authorized published source, review and follow its access terms and license,
and retain any restrictions on reuse or redistribution. The files stay local
and are ignored by Git. The script does not download data or connect to any
service. Validation selects the decision threshold; test is evaluated with
that threshold unchanged. Texts may recur across pairs, so pairs are not
independent observations.

Run the evaluation from the repository root with:

```powershell
python scripts/evaluate_stylometry_real.py
```

## Documentation
- `docs/architecture.md` — pipeline diagram and data model
- `docs/roadmap.md` — 80-day phased plan + honest full-scope estimate
- `docs/literature_gap_analysis.md` — existing tools vs. our contribution
- `docs/ethics_and_data_sources.md` — data sourcing rules and legal scope boundary

## Contributing (team workflow)
- One service folder per person/pair where practical
  (`infrastructure_scan`, `identity_graph`, `stylometry`, `fusion`/`llm_explain`).
- Branch per feature, PR into `main`, at least one teammate review before merge.
- Keep `docs/roadmap.md` milestones updated as phases complete.

## License
Academic/student project — license to be decided before any public release.
