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

_CONFIG_PATH = Path(__file__).resolve().with_name("config.json")
_CONFIG = json.loads(_CONFIG_PATH.read_text())
MIN_PILLAR_SCORE = float(_CONFIG["MIN_PILLAR_SCORE"])
SINGLE_SIGNAL_CAP = float(_CONFIG["SINGLE_SIGNAL_CAP"])
HARD_IDENTIFIER_MIN = float(_CONFIG["HARD_IDENTIFIER_MIN"])
HARD_IDENTIFIER_KINDS = {"pgp", "wallet", "cert_hash"}

# These cutoffs come from scripts/evaluate_retrieval.py on the synthetic dataset:
# the strong tier had 0 false positives among 2,556 pairs; tuned on this data,
# this result is not proven to generalise.
STRONG_TIER_THRESHOLD = 0.90
MODERATE_TIER_THRESHOLD = 0.70


def tier(confidence: float, *, single_signal: bool = False) -> str:
    """Map confidence to a tier; an uncorroborated result is always a lead."""
    if single_signal:
        return "lead"
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


def fuse(scores: SignalScores, weights: dict = None, evidence: dict | None = None) -> dict:
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
    raw_confidence = round(final, 3)
    pillar_scores = {
        "infrastructure": scores.infrastructure,
        "identity_graph": scores.identity_graph,
        "stylometry": scores.stylometry,
    }
    self_corroborating = any(
        pillar_scores.get(pillar, 0.0) >= HARD_IDENTIFIER_MIN
        and any(
            isinstance(item, dict) and item.get("kind") in HARD_IDENTIFIER_KINDS
            for item in items
        )
        for pillar, items in (evidence or {}).items()
    )
    single_signal = not self_corroborating and sum(
        score >= MIN_PILLAR_SCORE
        for score in pillar_scores.values()
    ) < 2
    confidence = round(min(raw_confidence, SINGLE_SIGNAL_CAP), 3) if single_signal else raw_confidence
    return {
        "confidence": confidence,
        "raw_confidence": raw_confidence,
        "single_signal": single_signal,
        "tier": tier(confidence, single_signal=single_signal),
        "breakdown": {
            "infrastructure": scores.infrastructure,
            "identity_graph": scores.identity_graph,
            "stylometry": scores.stylometry,
        },
        "weights_used": weights_used,
    }
