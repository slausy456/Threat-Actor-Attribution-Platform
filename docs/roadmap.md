# Roadmap

## Honest scope estimate
- **Full production vision** (autonomous continuous collection, live infra
  scanning, adversarial robustness): 18–24+ months, requires institutional
  authorization and resources beyond a student project.
- **Semester prototype** (this repo): ~80 days, built entirely on legal,
  published datasets.

## Phase 1 (this semester): Fusion prototype on legal datasets
See milestones below. Demonstrates the core novel contribution — the fusion
and explanation layer — end to end, on VeriDark and published DNM data.

### Milestones
- **Day 10** — All pillar tools/modules running independently on sample data;
  integration plan finalized.
- **Day 25** — Unified data model (Actor, Identifier, Relationship, Text,
  Confidence, Source, Timestamp) live; existing dataset outputs flow into a
  Neo4j graph; basic queries work.
- **Day 48** — AI fusion layer complete: combines graph signals + stylometric
  similarity, LLM-generated explanations, confidence scoring.
- **Day 68** — Streamlit dashboard complete: search, actor profile, graph
  view, timeline, confidence visualization, CSV/JSON export.
- **Day 80** — Final testing, documentation, architecture diagram, demo
  dry-run.

## Phase 2 (future work, not in this repo): Live data collection
Requires institutional legal authorization before any code here connects to
real Tor hidden services or live marketplaces. See
`docs/ethics_and_data_sources.md`.

## Phase 3 (future work): Adversarial robustness
Continuous adaptation to actors rotating identifiers, obfuscating writing
style, and improving OPSEC — an open research problem, not solved by this
prototype.
