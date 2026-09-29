"""
Fusion scorer — the core novel contribution of this project.

Combines three independent, individually-weak evidence signals into one
calibrated, explainable confidence score:

  1. infrastructure_scan signal  (0-1): clearnet/onion infra match strength
  2. identity_graph signal       (0-1): shared identifier overlap strength
  3. stylometry signal           (0-1): embedding similarity of text samples

Rationale: academic literature shows each signal alone is unreliable
(e.g. PGP-key reuse across Sybil accounts, vendors using multiple keys
deliberately — see docs/literature_gap_analysis.md). Fusing them, with
weights tunable per evidence quality, is the gap this project fills.
"""
from dataclasses import dataclass


@dataclass
class SignalScores:
    infrastructure: float  # 0.0 - 1.0
    identity_graph: float  # 0.0 - 1.0
    stylometry: float      # 0.0 - 1.0


DEFAULT_WEIGHTS = {
    "infrastructure": 0.35,
    "identity_graph": 0.35,
    "stylometry": 0.30,
}


def fuse(scores: SignalScores, weights: dict = None) -> dict:
    """
    Combine signal scores into one weighted confidence score.

    Returns a dict with the final score plus a per-signal breakdown, so the
    llm_explain module can generate a human-readable justification instead
    of a black-box number.
    """
    w = weights or DEFAULT_WEIGHTS
    final = (
        scores.infrastructure * w["infrastructure"]
        + scores.identity_graph * w["identity_graph"]
        + scores.stylometry * w["stylometry"]
    )
    return {
        "confidence": round(final, 3),
        "breakdown": {
            "infrastructure": scores.infrastructure,
            "identity_graph": scores.identity_graph,
            "stylometry": scores.stylometry,
        },
        "weights_used": w,
    }
