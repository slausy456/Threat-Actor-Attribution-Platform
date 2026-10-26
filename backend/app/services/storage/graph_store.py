"""In-memory persona and identifier graph backed by the project dataset."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import networkx as nx

from app.data_loader import load_personas
from app.models.entities import IdentifierType, Persona
from app.services.infrastructure_scan.matcher import _banner_score
from app.services.fusion.pipeline import score_pair
from app.services.llm_explain.explainer import explain_result

IDENTIFIER_WEIGHTS = {
    IdentifierType.PGP_KEY: 0.90,
    IdentifierType.WALLET: 0.85,
    IdentifierType.CERT_HASH: 0.90,
    IdentifierType.FAVICON_HASH: 0.70,
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class GraphStore:
    """Small in-memory graph and score cache; it never loads answer-key data."""

    def __init__(self, personas: dict[str, Persona] | None = None):
        self.personas = personas if personas is not None else load_personas()
        self.graph = nx.Graph()
        self._pair_cache: dict[tuple[str, str], dict] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        for persona_id, persona in self.personas.items():
            persona_node = ("persona", persona_id)
            self.graph.add_node(
                persona_node,
                kind="persona",
                persona_id=persona_id,
            )
            for identifier in persona.identifiers:
                if identifier.type == IdentifierType.HANDLE:
                    continue
                identifier_node = ("identifier", identifier.type.value, identifier.value)
                self.graph.add_node(
                    identifier_node,
                    kind="identifier",
                    identifier_type=identifier.type.value,
                    value=identifier.value,
                )
                self.graph.add_edge(
                    persona_node,
                    identifier_node,
                    weight=(
                        _banner_score(identifier.value)
                        if identifier.type == IdentifierType.SERVER_BANNER
                        else IDENTIFIER_WEIGHTS.get(identifier.type, 0.0)
                    ),
                )

    def get_persona(self, persona_id: str) -> Persona | None:
        return self.personas.get(persona_id)

    def list_personas(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Persona]:
        lower = _utc(since) if since is not None else None
        upper = _utc(until) if until is not None else None
        matches = []
        for persona in self.personas.values():
            first_seen = _utc(persona.first_seen)
            last_seen = _utc(persona.last_seen)
            if lower is not None and last_seen < lower:
                continue
            if upper is not None and first_seen > upper:
                continue
            matches.append(persona)
        return sorted(matches, key=lambda persona: persona.persona_id)

    def compare(self, a: str, b: str) -> dict:
        persona_a = self.get_persona(a)
        persona_b = self.get_persona(b)
        if persona_a is None or persona_b is None:
            raise KeyError(a if persona_a is None else b)

        cache_key = tuple(sorted((a, b)))
        if cache_key not in self._pair_cache:
            result = score_pair(persona_a, persona_b)
            result.update(explain_result(result))
            self._pair_cache[cache_key] = result
        return deepcopy(self._pair_cache[cache_key])

    def candidates(
        self,
        persona_id: str,
        top: int = 5,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict]:
        source = self.get_persona(persona_id)
        if source is None:
            raise KeyError(persona_id)
        matches = []
        for candidate in self.list_personas(since=since, until=until):
            if candidate.persona_id == persona_id:
                continue
            result = self.compare(persona_id, candidate.persona_id)
            matches.append({"persona": candidate, **result})
        matches.sort(key=lambda item: (-item["confidence"], item["persona"].persona_id))
        return matches[:top]

    def export_rows(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict]:
        return [
            {
                "persona_id": persona.persona_id,
                "marketplace": persona.marketplace,
                "handle": persona.handle,
                "first_seen": persona.first_seen.isoformat(),
                "last_seen": persona.last_seen.isoformat(),
                "identifiers": [
                    {"type": item.type.value, "value": item.value}
                    for item in persona.identifiers
                ],
                "text_sample_count": len(persona.texts),
            }
            for persona in self.list_personas(since=since, until=until)
        ]
