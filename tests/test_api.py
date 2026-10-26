import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.storage.graph_store import GraphStore

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_personas_and_filter_by_dates():
    all_personas = client.get("/personas")
    assert all_personas.status_code == 200
    assert len(all_personas.json()) > 1

    filtered = client.get(
        "/personas",
        params={"since": "2024-10-01T00:00:00", "until": "2024-10-31T23:59:59"},
    )
    assert filtered.status_code == 200
    assert filtered.json()
    assert all(
        persona["last_seen"] >= "2024-10-01T00:00:00"
        and persona["first_seen"] <= "2024-10-31T23:59:59"
        for persona in filtered.json()
    )


def test_get_persona_and_missing_persona():
    response = client.get("/personas/P001")
    assert response.status_code == 200
    assert response.json()["persona_id"] == "P001"
    assert client.get("/personas/not-a-persona").status_code == 404


def test_compare_has_fusion_and_explanation_fields():
    response = client.post("/compare", json={"a": "P001", "b": "P002"})
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["confidence"] <= 1.0
    assert set(body["breakdown"]) == {"identity_graph", "infrastructure", "stylometry"}
    assert body["evidence"]
    assert 20 <= len(body["explanation"]) <= 1200
    assert body["explanation_source"] in {"llm", "template"}
    assert body["fallback_reason"] is None if body["explanation_source"] == "llm" else bool(body["fallback_reason"])
    assert body["explanation_label"].startswith(("AI-generated (", "Template ("))
    assert client.post("/compare", json={"a": "P001", "b": "missing"}).status_code == 404
    assert client.post("/compare", json={"a": "P001"}).status_code == 422


def test_candidates_are_sorted_descending():
    response = client.get("/personas/P001/candidates", params={"top": 3})
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) == 3
    scores = [candidate["confidence"] for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(candidate["persona"]["persona_id"] != "P001" for candidate in candidates)
    assert client.get("/personas/missing/candidates").status_code == 404
    assert client.get("/personas/P001/candidates?top=0").status_code == 422


def test_export_csv_json_and_markdown_report():
    csv_response = client.get("/export", params={"format": "csv"})
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "persona_id" in csv_response.text

    json_response = client.get("/export", params={"format": "json"})
    assert json_response.status_code == 200
    assert json.loads(json_response.text)["rows"]

    report_response = client.get("/export", params={"format": "report"})
    assert report_response.status_code == 200
    assert "text/markdown" in report_response.headers["content-type"]
    assert report_response.text.startswith("# Persona Export")
    assert "human review" in report_response.text
    assert client.get("/export", params={"format": "xml"}).status_code == 422


def test_graph_store_builds_identifier_links_and_caches_scores(monkeypatch):
    import app.services.storage.graph_store as graph_store_module

    store = GraphStore()
    shared_identifier = ("identifier", "pgp_key", "PGP-SYN-2D1026706D7E805D")
    assert store.graph.has_edge(("persona", "P001"), shared_identifier)
    assert store.graph.has_edge(("persona", "P002"), shared_identifier)

    calls = []

    def fake_score_pair(persona_a, persona_b):
        calls.append((persona_a.persona_id, persona_b.persona_id))
        return {
            "confidence": 0.8,
            "breakdown": {},
            "weights_used": {},
            "evidence": {},
        }

    monkeypatch.setattr(graph_store_module, "score_pair", fake_score_pair)
    monkeypatch.setattr(
        graph_store_module,
        "explain_result",
        lambda result: {
            "explanation": "Tentative lead for human review.",
            "explanation_source": "template",
            "fallback_reason": "no_key",
            "explanation_label": "Template (no API key)",
        },
    )
    store.compare("P001", "P002")
    store.compare("P002", "P001")
    assert len(calls) == 1