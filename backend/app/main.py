"""
Threat Actor Attribution Platform — FastAPI backend entrypoint.

Wires together the four evidence pillars (infrastructure_scan, identity_graph,
stylometry, fusion) behind a single API. See docs/architecture.md.
"""
from fastapi import FastAPI

app = FastAPI(
    title="Threat Actor Attribution Platform",
    description=(
        "Multi-signal, confidence-scored attribution API. "
        "Operates only on legal, published research datasets — "
        "see docs/ethics_and_data_sources.md."
    ),
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers are registered here as each pillar's endpoints are implemented.
# from app.routers import actors, identifiers, matches
# app.include_router(actors.router)
# app.include_router(identifiers.router)
# app.include_router(matches.router)
