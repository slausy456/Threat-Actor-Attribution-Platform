"""
Identity-graph pillar: do two personas share identifiers?

CONTRACT (same for all pillars): compare(a, b) -> SignalResult
  - pure function, no I/O, no database (add Neo4j later behind this same signature)
  - symmetric: compare(a, b) == compare(b, a)
  - score in [0, 1]; evidence = short human-readable reasons

Signals available: HANDLE, PGP_KEY, WALLET  (see Persona.values_of)

Guidance:
  - exact PGP / wallet match = strong evidence
  - handle similarity = WEAK evidence (the 'similar_handle' trap must not score high)
  - no overlap at all -> low score, and say so in the evidence
Should succeed on: pgp_reuse, wallet_reuse, multi_signal
Expected to be blind to: infra_only, style_only   (that's what the other pillars are for)
"""
from __future__ import annotations

from difflib import SequenceMatcher
from math import prod

from app.models.entities import IdentifierType, Persona, SignalResult


def _score_handle_similarity(a_handle: str, b_handle: str) -> tuple[float, str] | None:
    """Return a weak similarity score for look-alike handles only."""
    a_norm = a_handle.lower()
    b_norm = b_handle.lower()
    ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
    if ratio < 0.88:
        return None
    weak_score = min(0.15, 0.08 + (ratio - 0.88) / 0.12 * 0.07)
    return weak_score, f"similar handles '{a_handle}' and '{b_handle}' (ratio {ratio:.2f})"


def compare(a: Persona, b: Persona) -> SignalResult:
    """Score shared identity signals using noisy-OR for independent evidence."""
    evidence: list[dict[str, str]] = []
    signal_scores: list[float] = []

    shared_pgp = a.values_of(IdentifierType.PGP_KEY) & b.values_of(IdentifierType.PGP_KEY)
    if shared_pgp:
        shared_value = sorted(shared_pgp)[0]
        signal_scores.append(0.90)
        evidence.append({"kind": "pgp", "description": f"shared PGP key {shared_value}"})

    shared_wallet = a.values_of(IdentifierType.WALLET) & b.values_of(IdentifierType.WALLET)
    if shared_wallet:
        shared_value = sorted(shared_wallet)[0]
        signal_scores.append(0.85)
        evidence.append({"kind": "wallet", "description": f"shared wallet {shared_value}"})

    shared_handles = a.values_of(IdentifierType.HANDLE) & b.values_of(IdentifierType.HANDLE)
    if shared_handles:
        handle_value = sorted(shared_handles)[0]
        signal_scores.append(0.15)
        evidence.append({"kind": "handle", "description": f"same handle {handle_value}"})

    for a_handle in a.values_of(IdentifierType.HANDLE):
        for b_handle in b.values_of(IdentifierType.HANDLE):
            if a_handle == b_handle:
                continue
            result = _score_handle_similarity(a_handle, b_handle)
            if result is not None:
                score, description = result
                signal_scores.append(score)
                evidence.append({"kind": "handle", "description": description})
                break
        else:
            continue
        break

    if not signal_scores:
        evidence.append({"kind": "none", "description": "no shared identifiers"})
        return SignalResult(score=0.0, evidence=evidence)

    score = 1.0 - prod(1.0 - s for s in signal_scores)
    has_strong_identity = bool(shared_pgp or shared_wallet)
    final_score = round(min(score, 0.99), 3)
    if not has_strong_identity:
        final_score = min(final_score, 0.15)
    return SignalResult(score=final_score, evidence=evidence)
