"""
Infrastructure pillar: do two personas run on the same server fingerprint?

CONTRACT (same for all pillars): compare(a, b) -> SignalResult
  - pure function; symmetric; score in [0, 1]; evidence = human-readable reasons

Signals available: CERT_HASH, FAVICON_HASH, SERVER_BANNER

Guidance:
  - matching cert hash / favicon hash = strong (rare, specific)
  - matching SERVER_BANNER = weak if the banner is common (e.g. 'nginx/1.18.0 (Ubuntu)');
    the 'shared_hosting' trap must not score high
  - Note: this operates on dataset records only — NO live scanning (see docs/ethics_and_data_sources.md)
Should succeed on: infra_only, multi_signal
Expected to be blind to: style_only
"""
from __future__ import annotations

from math import prod

from app.models.entities import IdentifierType, Persona, SignalResult

COMMON_BANNERS = {
    "nginx/1.18.0 (Ubuntu)",
    "Apache/2.4.41 (Ubuntu)",
}


def compare(a: Persona, b: Persona) -> SignalResult:
    """Score shared infrastructure fingerprints using noisy-OR."""
    evidence: list[str] = []
    signal_scores: list[float] = []

    shared_cert = a.values_of(IdentifierType.CERT_HASH) & b.values_of(IdentifierType.CERT_HASH)
    if shared_cert:
        shared_value = sorted(shared_cert)[0]
        signal_scores.append(0.90)
        evidence.append(f"shared certificate hash {shared_value}")

    shared_favicon = a.values_of(IdentifierType.FAVICON_HASH) & b.values_of(IdentifierType.FAVICON_HASH)
    if shared_favicon:
        shared_value = sorted(shared_favicon)[0]
        signal_scores.append(0.70)
        evidence.append(f"shared favicon hash {shared_value}")

    shared_banner = a.values_of(IdentifierType.SERVER_BANNER) & b.values_of(IdentifierType.SERVER_BANNER)
    for banner in sorted(shared_banner):
        if banner in COMMON_BANNERS:
            signal_scores.append(0.05)
            evidence.append(f"shared common banner {banner}")
        else:
            signal_scores.append(0.40)
            evidence.append(f"shared uncommon banner {banner}")

    if not signal_scores:
        evidence.append("no shared infrastructure fingerprints")
        return SignalResult(score=0.0, evidence=evidence)

    final_score = 1.0 - prod(1.0 - s for s in signal_scores)
    return SignalResult(score=round(min(final_score, 0.99), 3), evidence=evidence)
