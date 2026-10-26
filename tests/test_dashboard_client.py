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
    monkeypatch.setenv("LLM_API_KEY", "")
    from app.services.llm_explain import explainer
    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: pytest.fail("HTTP is disabled for fallback parity test"))
    explainer.reset_llm_controls()
    client._demo_store()._pair_cache.clear()
    demo_candidates = client.get_candidates("P001", top=5)
    assert client.connection_status() == client.DEMO_MODE_LABEL

    from fastapi.testclient import TestClient
    from app.main import app
    from urllib.parse import urlparse

    app.state.store._pair_cache.clear()
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


def test_score_all_pairs_sorts_once_in_batches(monkeypatch):
    from app.services.fusion import pipeline

    people = [PERSONA, {**PERSONA, "persona_id": "P002"}, {**PERSONA, "persona_id": "P003"}]
    def fake_score(a, b):
        confidence = 0.9 if {a.persona_id, b.persona_id} == {"P001", "P002"} else 0.7
        return {
            "confidence": confidence, "raw_confidence": confidence, "tier": "strong" if confidence == 0.9 else "moderate",
            "single_signal": False, "breakdown": {}, "evidence": {},
        }
    monkeypatch.setattr(pipeline, "score_pair", fake_score)
    batches = []
    result = client.score_all_pairs(people, batch_size=2, on_batch=lambda scored, total: batches.append((len(scored), total)))
    assert len(result) == 3
    assert [(row["persona_a"]["persona_id"], row["persona_b"]["persona_id"]) for row in result] == [
        ("P001", "P002"), ("P001", "P003"), ("P002", "P003")
    ]
    assert batches == [(2, 3), (3, 3)]


def test_persona_metrics_and_active_pair_filter():
    people = [PERSONA, {**PERSONA, "persona_id": "P002", "marketplace": "market_beta"}]
    pair = {"persona_a": people[0], "persona_b": people[1], "tier": "strong"}
    metrics = client.persona_metrics(people, [pair])
    assert metrics["personas"] == 2
    assert metrics["sources"] == 2
    assert metrics["identifiers"] == 2
    assert metrics["strong"] == 1
    assert client.filter_pairs([pair], {"P001": people[0], "P002": people[1]}) == [pair]
    assert client.filter_pairs([pair], {"P001": people[0]}) == []


def test_timeline_activity_clips_bars_and_counts_posts_by_week():
    person = {
        **PERSONA,
        "texts": [
            {"posted_at": "2024-02-05T10:00:00", "text": "one"},
            {"posted_at": "2024-03-01T10:00:00", "text": "two"},
        ],
    }
    result = client.timeline_activity([person], "2024-02-01", "2024-02-29")
    assert result["bars"][0]["last_seen"] == "2024-02-29T00:00:00"
    assert result["posts_per_week"] == [{"week": "2024-02-05", "Posts": 1}]


def test_pair_exports_support_markdown_and_csv():
    pair = {"persona_a": PERSONA, "persona_b": MATCH["persona"], "confidence": 0.92,
            "tier": "strong", "breakdown": {"identity_graph": 0.9}}
    markdown, markdown_mime = client.pairs_export_payload([pair], "markdown")
    csv_text, csv_mime = client.pairs_export_payload([pair], "csv")
    assert "# Scored pair report" in markdown and "P001" in markdown and markdown_mime == "text/markdown"
    assert list(csv.DictReader(csv_text.splitlines()))[0]["tier"] == "strong"
    assert csv_mime == "text/csv"


def test_explanation_source_label_uses_api_metadata():
    assert client.explanation_label({"explanation_label": "Template (no API key)"}) == "Template (no API key)"
    assert client.explanation_label({"explanation_label": "AI-generated (openai/gpt-oss-20b)"}) == \
        "AI-generated (openai/gpt-oss-20b)"


def _comparison_pair():
    return {
        "persona_a": PERSONA,
        "persona_b": MATCH["persona"],
        "confidence": 0.5,
        "breakdown": {"identity_graph": 0.0, "infrastructure": 0.0, "stylometry": 0.5},
        "evidence": {
            "identity_graph": [],
            "infrastructure": [],
            "stylometry": [{"kind": "style", "description": "style similarity is tentative"}],
        },
    }


def test_overview_scoring_makes_zero_llm_calls(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "sample-test-token-not-real")
    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: pytest.fail("overview must not call LLM"))
    batches = []
    rows = client.score_all_pairs([PERSONA, MATCH["persona"]], batch_size=1, on_batch=lambda scored, total: batches.append((len(scored), total)))
    assert len(rows) == 1
    assert batches == [(1, 1)]


def test_opening_pair_calls_llm_once_and_cached_pair_calls_none(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "sample-test-token-not-real")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    client.clear_explanation_cache()
    explainer.reset_llm_controls()
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "The evidence provides a tentative identity-graph signal."}}]}

    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: (calls.append(kwargs) or Response()))
    first = client.explain_pair(_comparison_pair(), budget_remaining=30)
    second = client.explain_pair(_comparison_pair(), budget_remaining=30)
    assert len(calls) == 1
    assert first["llm_calls_used"] == 1
    assert second["llm_calls_used"] == 0
    assert second["cached"] is True


def test_call_budget_prevents_llm_request(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "sample-test-token-not-real")
    client.clear_explanation_cache()
    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: pytest.fail("budget must block HTTP"))
    explanation = client.explain_pair(_comparison_pair(), budget_remaining=0)
    assert explanation["llm_calls_used"] == 0
    assert explanation["fallback_reason"] == "call_budget_exhausted"
    assert explanation["explanation_source"] == "template"
