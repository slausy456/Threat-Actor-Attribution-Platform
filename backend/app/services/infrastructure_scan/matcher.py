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
from app.models.entities import Persona, SignalResult


def compare(a: Persona, b: Persona) -> SignalResult:
    raise NotImplementedError("infrastructure_scan.compare — owner: TODO")
