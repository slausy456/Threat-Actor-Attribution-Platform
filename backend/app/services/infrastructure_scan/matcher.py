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

from functools import lru_cache
from math import prod

from app.data_loader import load_personas
from app.models.entities import IdentifierType, Persona, SignalResult

COMMON_BANNERS = {
    "nginx/1.18.0 (Ubuntu)",
    "Apache/2.4.41 (Ubuntu)",
}


@lru_cache(maxsize=1)
def _banner_persona_frequencies() -> dict[str, int]:
    """Count distinct dataset personas carrying each precomputed banner."""
    frequencies: dict[str, int] = {}
    for persona in load_personas().values():
        for banner in persona.values_of(IdentifierType.SERVER_BANNER):
            frequencies[banner] = frequencies.get(banner, 0) + 1
    return frequencies


def _banner_score(banner: str) -> float:
    """Rarer banners score higher; frequent dataset banners approach 0.05."""
    frequency = max(1, _banner_persona_frequencies().get(banner, 2))
    return round(max(0.05, min(0.30, 0.20 / frequency)), 3)


def compare(a: Persona, b: Persona) -> SignalResult:
    """Score shared infrastructure fingerprints using noisy-OR."""
    evidence: list[dict[str, str]] = []
    signal_scores: list[float] = []

    shared_cert = a.values_of(IdentifierType.CERT_HASH) & b.values_of(IdentifierType.CERT_HASH)
    if shared_cert:
        shared_value = sorted(shared_cert)[0]
        signal_scores.append(0.90)
        evidence.append({"kind": "cert_hash", "description": f"shared certificate hash {shared_value}"})

    shared_favicon = a.values_of(IdentifierType.FAVICON_HASH) & b.values_of(IdentifierType.FAVICON_HASH)
    if shared_favicon:
        shared_value = sorted(shared_favicon)[0]
        signal_scores.append(0.70)
        evidence.append({"kind": "favicon_hash", "description": f"shared favicon hash {shared_value}"})

    shared_banner = a.values_of(IdentifierType.SERVER_BANNER) & b.values_of(IdentifierType.SERVER_BANNER)
    for banner in sorted(shared_banner):
        banner_score = _banner_score(banner)
        if banner in COMMON_BANNERS:
            description = f"shared common banner {banner} (frequency score {banner_score:.3f})"
        else:
            description = f"shared uncommon banner {banner} (frequency score {banner_score:.3f})"
        evidence.append({"kind": "banner", "description": description})
        signal_scores.append(banner_score)

    if not signal_scores:
        evidence.append({"kind": "none", "description": "no shared infrastructure fingerprints"})
        return SignalResult(score=0.0, evidence=evidence)

    final_score = 1.0 - prod(1.0 - s for s in signal_scores)
    banner_only = bool(shared_banner) and not shared_cert and not shared_favicon
    if banner_only:
        final_score = min(final_score, 0.30)
    return SignalResult(score=round(min(final_score, 0.99), 3), evidence=evidence)
