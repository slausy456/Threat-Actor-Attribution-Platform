# Threat Actor Attribution Platform

**Problem Statement:** SIH26151 — Dark Web Threat Actor De-anonymization (NTRO / SIH 2026)
**Status:** Working research prototype (semester project). Results below are on synthetic data; see [Results and limitations](#results-and-limitations).

## What this is
A multi-signal attribution framework. Given two *personas* (one identity on one
marketplace), it estimates how likely they are the same real-world actor by
fusing three independent evidence pillars and explaining the result:

| Pillar | Looks at | How it scores |
|---|---|---|
| Identity graph | shared PGP keys, wallet addresses, handles | PGP ≈ 0.90, wallet ≈ 0.85, look-alike handles weak (≤ 0.15); noisy-OR |
| Infrastructure | certificate hashes, favicon hashes, server banners (from dataset fields only) | cert 0.90, favicon 0.70, banner by rarity (0.05–0.30); noisy-OR |
| Stylometry | writing style of text samples | `0.7 × char 3–5-gram TF-IDF cosine + 0.3 × nine-feature style-habit similarity` |

The three scores are combined by a logistic regression (weights in
`backend/app/services/fusion/weights.json`). Output is always a **lead for human
review, never proof**.

## What this is NOT (scope boundary — read this first)
- It does **not** scan, crawl or connect to Tor hidden services or live marketplaces.
  Everything runs on **synthetic data or published research datasets**
  (see `data/README.md` and `docs/ethics_and_data_sources.md`). The acceptance
  checker fails the build if code touches the network or Tor.
- Confidence is **not a calibrated probability**. It is a ranking aid; the cutoffs
  were chosen on synthetic data.
- Live infrastructure scanning is **future work** requiring institutional authorization
  (`docs/roadmap.md`).

## Why this exists (the gap)
Existing work tends to concentrate on one kind of evidence: OnionScan on
infrastructure leaks, VendorLink and sales-feature matching on vendor linking,
VeriDark on authorship verification. This project's contribution is the
combination: three independent pillars, a corroboration rule for when evidence
counts as supported, and an explanation an analyst can read.
See `docs/literature_gap_analysis.md`.

## Objectives
1. Implement a fusion engine combining identity, infrastructure and stylometric evidence into one explainable confidence score.
2. Evaluate it on legal data: a seeded synthetic dataset with explicit trap scenarios, and the published VeriDark benchmark for stylometry.
3. Generate plain-language, evidence-grounded explanations for each match (template by default; optional LLM with a grounding check).
4. Provide an analyst dashboard (search, compare, timeline, graph, export) with CSV/JSON/report export.
5. Keep a clear separation between this prototype and future live-deployment work.

## Repo layout
```
backend/        FastAPI service
  app/services/identity_graph/        PGP / wallet / handle correlation
  app/services/infrastructure_scan/   certificate, favicon, banner matching (dataset fields only)
  app/services/stylometry/            char n-gram TF-IDF + style-habit features
  app/services/fusion/                logistic fusion, tiers, single-signal cap
  app/services/llm_explain/           template explanations; optional LLM
  app/services/storage/               in-memory NetworkX persona graph
frontend/       React + TypeScript + Vite web UI: overview, search, compare, timeline, graph, export
dashboard/      legacy Streamlit prototype, superseded by frontend/ (kept for reference; safe to remove)
data/           synthetic/ (committed), veridark/ (local only, git-ignored), raw/ processed/
docker/         docker-compose.yml — Neo4j + Postgres: NOT used by the current prototype
docs/           architecture, roadmap, ethics/data-sourcing, literature gap, confidence tiers
scripts/        evaluation, training, acceptance checker, data generation
tests/          unit and integration tests
```

## Tech stack
- **Backend:** Python 3.11+, FastAPI, scikit-learn, NetworkX
- **Storage:** in-memory NetworkX graph (a database is future work; `docker/` is a placeholder for it)
- **Stylometry:** character n-gram TF-IDF and style features (no neural embeddings, no model download, no GPU)
- **Explanations:** deterministic template by default; optional Groq or OpenAI model with an evidence-grounding check
- **Frontend:** React 18 + Vite + TypeScript + Tailwind, Recharts, Framer Motion and a Three.js background (the only supported UI)

## Quickstart
Needs Python 3.11+, Node.js 18+ and Git. No database, Docker service or LLM key is required.

**1. Backend (terminal 1)**
```bash
git clone <this-repo-url>
cd <repo-folder>
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --port 8000
```
The API is at `http://127.0.0.1:8000`, with interactive docs at `/docs`.

**2. Web UI (terminal 2)**
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`. Vite proxies `/api/*` to `http://127.0.0.1:8000`, so the API must be running first. To use a separate API host, set `VITE_API_BASE_URL` (the API must allow browser CORS).

| Route | View |
|---|---|
| `/` | Overview and ranked candidate leads |
| `/search` | Persona search |
| `/compare` | Pair comparison with pillar scores, tier and evidence |
| `/timeline` | Dataset activity and persona lifetimes |
| `/graph` | Relationship graph of candidate links |
| `/export` | JSON, CSV and Markdown report export |

**API endpoints:** `GET /health`, `GET /personas`, `GET /personas/{id}`, `POST /compare`,
`GET /personas/{id}/candidates`, `GET /export?format=csv|json|report`. The `since` and `until`
filters select personas whose observed date range overlaps the interval.

**Production build:** `cd frontend && npm run build` (type-checks, then writes `frontend/dist/`).

### Explanation layer
Without a key, explanations come from a deterministic template. To use an LLM, copy
`.env.example` to `.env` and set:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `groq` or `openai` |
| `LLM_API_KEY` | key for the provider (never logged or returned) |
| `LLM_MODEL` | model name (default for Groq: `openai/gpt-oss-20b`) |

Check connectivity with `python scripts/check_llm.py`. Each explanation is labelled
**AI-generated (`<model>`)** (passed evidence validation) or **Template (`<reason>`)**.
Both are qualitative and not proof.

## Confidence tiers
Results include `tier`, `single_signal` and the uncapped `raw_confidence`. A pillar
*qualifies* at a score of 0.30 or more. A result is *corroborated* if at least two
pillars qualify, or if it rests on a hard identifier (PGP key, wallet or certificate
hash scoring 0.85 or more). Uncorroborated results are capped at 0.65 and labelled `lead`.

| Tier | Condition |
|---|---|
| Strong | confidence ≥ 0.90, corroborated |
| Moderate | 0.70 ≤ confidence < 0.90, corroborated |
| Weak | confidence < 0.70, corroborated |
| Lead | fewer than two qualifying pillars and no hard identifier (capped at 0.65) |

Cutoffs were tuned on the synthetic dataset and are not proven to generalise.
See [docs/confidence_tiers.md](docs/confidence_tiers.md).

## Results and limitations
Reproduce with `python scripts/evaluate_pillars.py` and `python scripts/evaluate_retrieval.py`.

**Synthetic data** (72 personas, 12 scenarios including trap cases: shared hosting, copycat style, look-alike handles):
- 53 labelled pairs, threshold 0.5: fused F1 ≈ 0.96–0.98 (in-sample), nested GroupKFold CV by actor: precision, recall, F1 = 0.958. Single pillars: identity 0.74, stylometry 0.70, infrastructure 0.50.
- All 2,556 pairs: top-1 0.938, top-3 1.000, MRR 0.965. At fused thresholds 0.7 / 0.8 / 0.9: precision 1.000, recall 0.833, 0 false positives. At 0.5 there are 150 false positives, all style-only pairs held at the 0.65 lead cap.

**Real text — a negative result.** On a pair-verification split of VeriDark our stylometry
does **not** work: AUC 0.41 / 0.45 / 0.46 (train / val / test), which is at or below chance.
Its content-similarity component points the wrong way on that data; a punctuation-and-capitalisation
profile reaches AUC 0.70–0.76 in a post-hoc check. A real-text style scorer is future work.

**Other limits:** small training set (53 pairs); synthetic data authored by the same team;
persona pairs only (no clustering of three or more); in-memory store.

## Running tests and checks
From the repo root:
```bash
python scripts/generate_synthetic_data.py   # only if data/synthetic is missing
python -m pytest tests -q                    # 96 tests pass on main
python scripts/check_acceptance.py           # acceptance checker: no FAIL lines expected
```
**Do not run `scripts/train_fusion.py` casually:** it overwrites the committed
`weights.json`; retraining on the current pillar scores makes the shared-hosting trap
fail the acceptance checker. If it was run by mistake, restore with
`git checkout -- backend/app/services/fusion/weights.json`.
If a protected file is deliberately changed, review it and re-baseline with
`python scripts/check_acceptance.py --update-hashes`.

## Data
See `data/README.md` before adding anything to `data/`. Only legal, published
research datasets are permitted — no live-scraped dark web data.

### VeriDark stylometry evaluation (optional, local only)
VeriDark is used under its access terms: not redistributed, not used in public demos.
Place locally obtained files under `data/veridark/` (git-ignored), one JSON file per pair:

```text
data/veridark/
   train/<pair>.json
   val/<pair>.json
   test/<pair>.json
```
Each file: `{"id": "...", "pair": ["text1", "text2"], "same": true}`. The evaluator reads only
these three folders, selects the threshold on validation and applies it unchanged to test.
Texts recur across pairs, so pairs are not independent. Run:

```bash
python scripts/evaluate_stylometry_real.py
```

## Documentation
- `docs/architecture.md` — pipeline and data model
- `docs/pillar_contract.md` — the `compare(a, b)` contract every pillar implements
- `docs/confidence_tiers.md` — tier rules and caveats
- `docs/roadmap.md` — phased plan
- `docs/literature_gap_analysis.md` — existing tools vs. this project
- `docs/ethics_and_data_sources.md` — data sourcing rules and legal scope

## Contributing
- Branch per feature, PR into `main`, one teammate review before merge.
- Run `python -m pytest tests -q` and `python scripts/check_acceptance.py` before every commit.
- Do not commit datasets, keys, `node_modules/` or `dist/`.

## License
Academic/student project — license to be decided before any public release.
