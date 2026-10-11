import csv
import json

import pytest

from dashboard import client


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


PERSONA = {
    "persona_id": "P001",
    "marketplace": "market_alpha",
    "handle": "silver_fox",
    "first_seen": "2024-01-01T00:00:00",
    "last_seen": "2024-04-01T00:00:00",
    "identifiers": [{"type": "pgp_key", "value": "PGP-SYN-ABCD1234"}],
    "texts": [],
}

MATCH = {
    "persona": {
        **PERSONA,
        "persona_id": "P002",
        "handle": "copper_owl",
        "identifiers": [{"type": "wallet", "value": "bc1qsynsample123456789"}],
    },
    "confidence": 0.92,
    "tier": "strong",
    "breakdown": {"identity_graph": 0.9, "infrastructure": 0.0, "stylometry": 0.8},
    "evidence": {"identity_graph": ["shared PGP key PGP-SYN-ABCD1234"]},
    "explanation": "Tier: strong lead; evidence remains uncertain.",
}


def test_api_url_is_configurable_but_loopback_only(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://localhost:8123/")
    assert client.api_base_url() == "http://localhost:8123"
    with pytest.raises(ValueError, match="local HTTP"):
        client.api_base_url("https://example.com")


def test_list_personas_and_candidates_shape_timeline_params(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://127.0.0.1:8000")
    calls = []

    def fake_request(method, url, timeout, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse([PERSONA] if url.endswith("/personas") else [MATCH])

    monkeypatch.setattr(client.requests, "request", fake_request)
    client.list_personas(since="2024-01-01", until="2024-02-01")
    client.get_candidates("P001", top=4, since="2024-01-01", until="2024-02-01")

    assert calls[0][2]["params"] == {"since": "2024-01-01", "until": "2024-02-01"}
    assert calls[1][2]["params"] == {
        "top": 4,
        "since": "2024-01-01",
        "until": "2024-02-01",
    }


def test_search_matches_id_handle_and_identifier():
    people = [PERSONA, {**PERSONA, "persona_id": "P002", "handle": "other"}]
    assert client.search_personas("p001", people) == [PERSONA]
    assert client.search_personas("SILVER", people) == [PERSONA]
    assert client.search_personas("abcd12", people) == people


def test_linked_personas_returns_exact_shared_identifiers():
    other = {
        **PERSONA,
        "persona_id": "P002",
        "identifiers": [
            {"type": "pgp_key", "value": "PGP-SYN-ABCD1234"},
            {"type": "wallet", "value": "bc1qother"},
        ],
    }
    links = client.linked_personas(PERSONA, [PERSONA, other])
    assert len(links) == 1
    assert links[0]["persona"]["persona_id"] == "P002"
    assert links[0]["shared_identifiers"] == [
        {"type": "pgp_key", "value": "PGP-SYN-ABCD1234"}
    ]


def test_compare_uses_local_api_and_json_body(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://127.0.0.1:8000")
    calls = []

    def fake_request(method, url, timeout, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse({"confidence": 0.5})

    monkeypatch.setattr(client.requests, "request", fake_request)
    result = client.compare_personas("P001", "P002")
    assert result["confidence"] == 0.5
    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://127.0.0.1:8000/compare"
    assert calls[0][2]["json"] == {"a": "P001", "b": "P002"}


def test_candidate_graph_labels_edges_and_tiers():
    figure = client.build_candidate_graph(PERSONA, [MATCH])
    assert figure.layout.annotations[0].text == "Identity graph"
    assert figure.layout.annotations[0].bordercolor == client.TIER_COLORS["strong"]
    assert any(trace.name == "Strong" for trace in figure.data)


def test_candidate_export_uses_api_export_and_contains_shown_matches(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://127.0.0.1:8000")
    calls = []
    export_payload = {
        "rows": [
            {
                "persona_id": "P002",
                "marketplace": "market_alpha",
                "handle": "copper_owl",
                "first_seen": "2024-01-01T00:00:00",
                "last_seen": "2024-04-01T00:00:00",
                "identifiers": [{"type": "wallet", "value": "bc1qsynsample123456789"}],
            },
            {"persona_id": "P003", "marketplace": "market_beta", "handle": "not_shown"},
        ]
    }

    def fake_request(method, url, timeout, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(export_payload)

    monkeypatch.setattr(client.requests, "request", fake_request)
    csv_text, csv_mime = client.candidate_export_payload([MATCH], "csv")
    json_text, json_mime = client.candidate_export_payload([MATCH], "json")

    assert len(calls) == 2
    assert all(call[1] == "http://127.0.0.1:8000/export" for call in calls)
    assert all(call[2]["params"]["format"] == "json" for call in calls)
    assert csv_mime == "text/csv"
    assert list(csv.DictReader(csv_text.splitlines()))[0]["tier"] == "strong"
    assert json_mime == "application/json"
    exported = json.loads(json_text)
    assert len(exported) == 1
    assert exported[0]["persona_id"] == "P002"
    assert exported[0]["confidence"] == 0.92


def test_demo_candidates_and_tiers_match_api_path_for_p001(monkeypatch):
    monkeypatch.delenv("ATTRIBUTION_API_URL", raising=False)
    demo_candidates = client.get_candidates("P001", top=5)
    assert client.connection_status() == client.DEMO_MODE_LABEL

    from fastapi.testclient import TestClient
    from app.main import app
    from urllib.parse import urlparse

    api_client = TestClient(app)

    def api_request(method, url, timeout, **kwargs):
        kwargs.pop("timeout", None)
        return api_client.request(method, urlparse(url).path, **kwargs)

    monkeypatch.setattr(client.requests, "request", api_request)
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://127.0.0.1:8000")
    api_candidates = client.get_candidates("P001", top=5)

    assert client.connection_status() == client.CONNECTED_MODE_LABEL
    assert demo_candidates == api_candidates
    assert [item["tier"] for item in demo_candidates] == [item["tier"] for item in api_candidates]


def test_unreachable_api_falls_back_to_demo(monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_API_URL", "http://127.0.0.1:8000")

    def unavailable(*args, **kwargs):
        raise client.requests.ConnectionError("offline")

    monkeypatch.setattr(client.requests, "request", unavailable)
    candidates = client.get_candidates("P001", top=2)
    assert len(candidates) == 2
    assert client.connection_status() == client.DEMO_MODE_LABEL