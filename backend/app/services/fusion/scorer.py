"""Fusion scorer for the three evidence pillars.

The runtime service remains label-free: it loads a learned model from a JSON file
that was trained in scripts/train_fusion.py using the synthetic dataset. The
score is a monotonic logistic transform of the pillar scores, which keeps the
final confidence in [0, 1] and preserves the ordering implied by more evidence.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


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

# These cutoffs come from scripts/evaluate_retrieval.py on the synthetic dataset:
# the strong tier had 0 false positives among 2,556 pairs; tuned on this data,
# this result is not proven to generalise.
STRONG_TIER_THRESHOLD = 0.90
MODERATE_TIER_THRESHOLD = 0.70


def tier(confidence: float) -> str:
    """Map a confidence score to a descriptive tier without changing the score."""
    if confidence >= STRONG_TIER_THRESHOLD:
        return "strong"
    if confidence >= MODERATE_TIER_THRESHOLD:
        return "moderate"
    return "weak"


def _load_model_weights() -> dict | None:
    path = Path(__file__).resolve().with_name("weights.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    required = {"identity_graph", "infrastructure", "stylometry"}
    if not required.issubset(payload):
        return None
    return {
        "intercept": float(payload.get("intercept", 0.0)),
        "identity_graph": float(payload["identity_graph"]),
        "infrastructure": float(payload["infrastructure"]),
        "stylometry": float(payload["stylometry"]),
    }


def fuse(scores: SignalScores, weights: dict = None) -> dict:
    """
    Combine signal scores into one weighted confidence score.

    Returns a dict with the final score plus a per-signal breakdown, so the
    llm_explain module can generate a human-readable justification instead
    of a black-box number.
    """
    w = weights or _load_model_weights() or DEFAULT_WEIGHTS
    if set({"identity_graph", "infrastructure", "stylometry"}).issubset(w):
        intercept = float(w.get("intercept", 0.0))
        logit = (
            intercept
            + scores.identity_graph * float(w["identity_graph"])
            + scores.infrastructure * float(w["infrastructure"])
            + scores.stylometry * float(w["stylometry"])
        )
        final = 1.0 / (1.0 + math.exp(-logit))
        weights_used = {
            "intercept": intercept,
            "identity_graph": float(w["identity_graph"]),
            "infrastructure": float(w["infrastructure"]),
            "stylometry": float(w["stylometry"]),
        }
    else:
        final = (
            scores.infrastructure * w["infrastructure"]
            + scores.identity_graph * w["identity_graph"]
            + scores.stylometry * w["stylometry"]
        )
        weights_used = w.copy()
    return {
        "confidence": round(final, 3),
        "tier": tier(round(final, 3)),
        "breakdown": {
            "infrastructure": scores.infrastructure,
            "identity_graph": scores.identity_graph,
            "stylometry": scores.stylometry,
        },
        "weights_used": weights_used,
    }
