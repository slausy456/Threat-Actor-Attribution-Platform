# Architecture

```
                    ┌─────────────────────────┐
                    │   data/veridark/         │
                    │   data/processed/         │  (legal, published datasets only)
                    └───────────┬───────────────┘
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                         ▼
┌──────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ infrastructure│      │  identity_graph   │      │   stylometry      │
│   _scan       │      │  (PGP/handle/     │      │ (sentence-        │
│ (dataset-based│      │   wallet corr.)   │      │  transformers      │
│  fingerprint  │      │                    │      │  embeddings)       │
│  matching)    │      │                    │      │                    │
└───────┬───────┘      └─────────┬──────────┘      └─────────┬──────────┘
        │                        │                            │
        └────────────────────────┼────────────────────────────┘
                                  ▼
                        ┌──────────────────┐
                        │      fusion        │   combines all 3 signals into
                        │  (confidence score)│   one calibrated, weighted score
                        └─────────┬──────────┘
                                  ▼
                        ┌──────────────────┐
                        │   llm_explain      │   generates plain-language
                        │                    │   reasoning per match
                        └─────────┬──────────┘
                                  ▼
                        ┌──────────────────┐
                        │   Neo4j graph DB   │
                        │  + Postgres         │
                        └─────────┬──────────┘
                                  ▼
                        ┌──────────────────┐
                        │  FastAPI backend   │
                        └─────────┬──────────┘
                                  ▼
                        ┌──────────────────┐
                        │ Streamlit dashboard │  search, actor profile,
                        │                     │  graph view, timeline,
                        │                     │  confidence viz, export
                        └──────────────────┘
```

## Data model (core entities)
- **Actor** — a suspected real-world entity
- **Identifier** — handle, PGP key, wallet address, associated with an Actor
- **Relationship** — link between identifiers/actors with a type and weight
- **Text** — stylometric sample (post/listing) tied to an Identifier
- **Confidence** — fused score + explanation, tied to a Relationship or Actor match
- **Source** — dataset/document the evidence came from
- **Timestamp** — when the evidence was recorded (for timeline queries)
