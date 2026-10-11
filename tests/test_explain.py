import re

from app.data_loader import load_ground_truth, load_personas
from app.services.fusion.pipeline import score_pair
from app.services.llm_explain import explain


def _example_result(confidence=0.2):
    return {
        "confidence": confidence,
        "breakdown": {
            "identity_graph": 0.0,
            "infrastructure": 0.05,
            "stylometry": 0.34,
        },
        "weights_used": {},
        "evidence": {
            "identity_graph": ["no shared identifiers"],
            "infrastructure": ["shared certificate hash 0123456789abcdef"],
            "stylometry": ["character n-gram similarity 0.34"],
        },
    }


def test_explain_returns_bounded_string_without_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = explain(_example_result())
    assert isinstance(result, str)
    assert 20 <= len(result) <= 1200


def test_explain_only_includes_identifiers_from_evidence(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = explain(_example_result())
    evidence = " ".join(
        item
        for items in _example_result()["evidence"].values()
        for item in items
    )
    identifiers = re.compile(
        r"\b(?:PGP(?:-SYN)?-[A-Z0-9-]{4,}|bc1[a-z0-9]{10,}|0x[a-f0-9]{16,}|[a-f0-9]{16,})\b",
        re.IGNORECASE,
    )
    assert {value.lower() for value in identifiers.findall(result)} <= {
        value.lower() for value in identifiers.findall(evidence)
    }


def test_explain_uses_uncertainty_and_human_review_language(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = explain(_example_result())
    assert re.search(r"uncertain|tentative|possible|limited|confidence", result, re.I)
    assert re.search(r"lead for human review|not proof", result, re.I)
    assert result.endswith("Treat this as a lead for human review, not proof of attribution.")


def test_zero_score_without_evidence_is_reported_as_missing_not_weak(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = explain(
        {
            "confidence": 0.2,
            "breakdown": {"identity_graph": 0.0, "infrastructure": 0.0, "stylometry": 0.0},
            "evidence": {"identity_graph": [], "infrastructure": [], "stylometry": []},
        }
    )
    assert "no shared identity evidence was found" in result
    assert "no shared infrastructure evidence was found" in result
    assert "no shared writing-style evidence was found" in result
    assert "evidence is weak (0.000)" not in result


def test_signal_is_called_weak_only_for_nonzero_score_below_point_three(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = explain(
        {
            "confidence": 0.3,
            "breakdown": {"identity_graph": 0.0, "infrastructure": 0.299, "stylometry": 0.30},
            "evidence": {
                "identity_graph": [],
                "infrastructure": ["shared common banner nginx/1.18"],
                "stylometry": ["style similarity 0.30"],
            },
        }
    )
    assert "infrastructure evidence is weak (0.299)" in result
    assert "identity evidence is weak" not in result
    assert "writing style evidence is weak" not in result


def test_tier_hedge_uses_corroboration_and_three_decimal_confidence(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    strong = explain(
        {
            "confidence": 0.9,
            "breakdown": {"identity_graph": 0.3, "infrastructure": 0.30, "stylometry": 0.0},
            "evidence": {},
        }
    )
    assert "Confidence is 0.900 (strong tier)" in strong
    assert "several independent signals agree; still a lead for human review" in strong

    moderate = explain(
        {
            "confidence": 0.7,
            "breakdown": {"identity_graph": 0.30, "infrastructure": 0.0, "stylometry": 0.0},
            "evidence": {},
        }
    )
    assert "Confidence is 0.700 (moderate tier); this rests on a single signal." in moderate

    weak = explain({"confidence": 0.699, "breakdown": {}, "evidence": {}})
    assert "Confidence is 0.699 (weak tier); this is tentative." in weak


def test_low_confidence_explanation_does_not_assert_same_actor(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    personas = load_personas()
    _, pairs = load_ground_truth()
    negative_pair = next(pair for pair in pairs if not pair.same_actor)
    result = score_pair(personas[negative_pair.persona_a], personas[negative_pair.persona_b])
    assert result["confidence"] < 0.5
    explanation = explain(result)
    assert not re.search(r"they are the same actor", explanation, re.I)
    assert re.search(r"tentative|possible|limited|low confidence", explanation, re.I)


def test_configured_llm_uses_ten_second_timeout(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    response_text = "The available evidence supports a limited identity-graph signal."
    calls = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": response_text}}]}

    def fake_post(*args, **kwargs):
        calls.update(kwargs)
        return Response()

    monkeypatch.setattr(explainer.httpx, "post", fake_post)
    explanation = explain(_example_result())
    assert response_text in explanation
    assert explanation.startswith("Confidence is 0.200 (weak tier)")
    assert explanation.endswith("Treat this as a lead for human review, not proof of attribution.")
    assert calls["timeout"] == 10.0


def test_llm_identifier_not_in_evidence_uses_template(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Confidence is tentative. PGP-SYN-FAKE1234 is shared evidence. "
                                "Treat this as a lead for human review, not proof."
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: Response())
    explanation = explain(_example_result())
    assert "PGP-SYN-FAKE1234" not in explanation
    assert "lead for human review" in explanation