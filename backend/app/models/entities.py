"""
Core data model shared by every pillar (see docs/architecture.md).

Design decision: the unit we compare is a *Persona* — one identity as it
appears on one marketplace/forum. The whole system answers one question:

    "Are persona A and persona B the same real-world actor?"

Each pillar takes (persona_a, persona_b) and returns a SignalResult.
The fusion module combines the three SignalResults into one confidence.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class IdentifierType(str, Enum):
    # identity_graph pillar uses these
    HANDLE = "handle"
    PGP_KEY = "pgp_key"
    WALLET = "wallet"
    # infrastructure_scan pillar uses these
    CERT_HASH = "cert_hash"
    FAVICON_HASH = "favicon_hash"
    SERVER_BANNER = "server_banner"


IDENTITY_TYPES = {IdentifierType.HANDLE, IdentifierType.PGP_KEY, IdentifierType.WALLET}
INFRA_TYPES = {
    IdentifierType.CERT_HASH,
    IdentifierType.FAVICON_HASH,
    IdentifierType.SERVER_BANNER,
}


class Identifier(BaseModel):
    type: IdentifierType
    value: str


class TextSample(BaseModel):
    """One post/listing/message written by a persona (input to stylometry)."""

    text: str
    posted_at: datetime


class Persona(BaseModel):
    """One identity on one marketplace. The thing we compare."""

    persona_id: str
    marketplace: str  # the Source of this evidence
    handle: str
    identifiers: list[Identifier] = Field(default_factory=list)
    texts: list[TextSample] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime

    def values_of(self, *types: IdentifierType) -> set[str]:
        """All identifier values of the given type(s), as a set."""
        wanted = set(types)
        return {i.value for i in self.identifiers if i.type in wanted}


class SignalResult(BaseModel):
    """What every pillar returns. Matches the inputs fusion/scorer.py expects."""

    score: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)  # human-readable reasons


# ---------------------------------------------------------------------------
# Ground truth — only exists for synthetic data. Real data has no answer key.
# ---------------------------------------------------------------------------


class Actor(BaseModel):
    actor_id: str
    persona_ids: list[str]


class PairLabel(BaseModel):
    persona_a: str
    persona_b: str
    same_actor: bool
    scenario: str  # which test case this pair represents (see generator)
