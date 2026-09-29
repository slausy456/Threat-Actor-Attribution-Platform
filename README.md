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
  app/services/identity_graph/        PGP/handle/wallet correlation, Neo4j
  app/services/stylometry/            sentence-transformers embedding similarity
  app/services/fusion/                combines signals into one confidence score
  app/services/llm_explain/           generates plain-language reasoning per match
dashboard/      Streamlit UI: search, actor profile, graph view, export
data/           raw/processed/veridark — see data/README.md before adding anything
docker/         docker-compose for Neo4j + Postgres + backend + dashboard
docs/           architecture, roadmap, ethics/data-sourcing, literature gap analysis
scripts/        setup and dev helper scripts
tests/          unit/integration tests
```

## Tech stack
- **Backend:** Python 3.11+, FastAPI
- **Graph DB:** Neo4j | **Structured DB:** PostgreSQL
- **Stylometry:** sentence-transformers (embedding similarity)
- **Explanation layer:** LLM API (Groq / OpenAI / Gemini — pick one, see `.env.example`)
- **Dashboard:** Streamlit
- **Infra:** Docker Compose

## Prerequisites
- Python 3.11+
- Docker + Docker Compose
- Git
- An API key for your chosen LLM provider (for the `llm_explain` module)

## Quickstart
```bash
git clone <this-repo-url>
cd threat-actor-attribution

# 1. Start infra (Neo4j + Postgres)
cd docker && docker compose up -d && cd ..

# 2. Configure environment
cp .env.example .env
# edit .env with your local DB credentials and LLM API key

# 3. Set up backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# backend now running at http://localhost:8000  (see /health)

# 4. Set up dashboard (new terminal)
cd dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
# dashboard now running at http://localhost:8501
```
Or just run `bash scripts/setup.sh` to bootstrap both virtual environments at once.

## Running tests
```bash
cd backend && source .venv/bin/activate
pytest ../tests
```
(Test suite is a placeholder — add tests alongside each service module as it's built.)

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
