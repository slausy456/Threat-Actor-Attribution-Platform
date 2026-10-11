"""FastAPI entrypoint for the in-memory research-data prototype."""
from fastapi import FastAPI

from app.routers.api import router
from app.services.storage.graph_store import GraphStore

app = FastAPI(
    title="Threat Actor Attribution Platform",
    description=(
        "Multi-signal, confidence-scored attribution API. "
        "Operates only on legal, published research datasets — "
        "see docs/ethics_and_data_sources.md."
    ),
    version="0.1.0",
)
app.state.store = GraphStore()
app.include_router(router)
