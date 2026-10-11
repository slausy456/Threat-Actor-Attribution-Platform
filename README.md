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
- **Explanation layer:** LLM API (Groq / OpenAI / Gemini — pick one, see `.env.example`)
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

Available endpoints: `GET /health`, `GET /personas`, `GET /personas/{id}`, `POST /compare`, `GET /personas/{id}/candidates`, and `GET /export?format=csv|json|report`. The `since` and `until` filters select personas whose observed date range overlaps the requested interval.

### Confidence tiers

API comparison and candidate results include an additive tier; the underlying confidence score is unchanged.

| Tier | Fused confidence |
|---|---:|
| Strong | >= 0.90 |
| Moderate | >= 0.70 and < 0.90 |
| Weak | < 0.70 |

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
