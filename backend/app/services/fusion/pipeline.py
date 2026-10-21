"""Glue: run all three pillars on a pair and fuse the result."""
from app.models.entities import Persona
from app.services.fusion.scorer import SignalScores, fuse
from app.services.identity_graph import matcher as identity
from app.services.infrastructure_scan import matcher as infra
from app.services.stylometry import matcher as style


def score_pair(a: Persona, b: Persona, weights: dict | None = None) -> dict:
    """Fused confidence + per-pillar breakdown + evidence, for one persona pair."""
    results = {
        "identity_graph": identity.compare(a, b),
        "infrastructure": infra.compare(a, b),
        "stylometry": style.compare(a, b),
    }
    fused = fuse(
        SignalScores(
            infrastructure=results["infrastructure"].score,
            identity_graph=results["identity_graph"].score,
            stylometry=results["stylometry"].score,
        ),
        weights,
        evidence={k: v.evidence for k, v in results.items()},
    )
    fused["evidence"] = {k: v.evidence for k, v in results.items()}
    return fused
