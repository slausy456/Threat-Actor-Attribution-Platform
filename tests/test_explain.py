import re

import pytest

from app.data_loader import load_ground_truth, load_personas
from app.services.fusion.pipeline import score_pair
from app.services.llm_explain import explain


@pytest.fixture(autouse=True)
def reset_process_llm_controls():
    from app.services.llm_explain import explainer

    explainer.reset_llm_controls()
    yield
    explainer.reset_llm_controls()


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
            "confidence": 0.65,
            "single_signal": True,
            "breakdown": {"identity_graph": 0.30, "infrastructure": 0.0, "stylometry": 0.0},
            "evidence": {},
        }
    )
    assert "Confidence is 0.650 (lead tier); fewer than two pillars corroborate this lead, so the result is tentative." in moderate

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


def _configure_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sample-test-token-not-real")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("LLM_MODEL", raising=False)


def _status_response(status_code):
    import httpx

    class Response:
        def raise_for_status(self):
            request = httpx.Request("POST", "https://provider.example.test")
            response = httpx.Response(status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    return Response()


def test_valid_llm_response_reports_llm_source(monkeypatch):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "The evidence provides a tentative identity-graph signal."}}]}

    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: Response())
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "llm"
    assert result["fallback_reason"] is None
    assert result["explanation_label"] == "AI-generated (openai/gpt-oss-20b)"


def test_missing_key_reports_no_key_fallback(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: pytest.fail("HTTP must not be called"))
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "template"
    assert result["fallback_reason"] == "no_key"
    assert result["explanation_label"] == "Template (no API key)"


def test_groq_default_model_is_account_supported(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert explainer.configured_model() == "openai/gpt-oss-20b"


def test_two_429_responses_open_breaker_and_later_use_template(monkeypatch):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)
    explainer.reset_llm_controls()
    slept = []
    monkeypatch.setattr(explainer.time, "sleep", lambda seconds: slept.append(seconds))
    calls = []

    def rate_limited(*args, **kwargs):
        calls.append(kwargs)
        import httpx
        request = httpx.Request("POST", "https://provider.example.test")
        response = httpx.Response(429, request=request, headers={"Retry-After": "2"})
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    monkeypatch.setattr(explainer.httpx, "post", rate_limited)
    first = explainer.explain_result(_example_result())
    later = explainer.explain_result(_example_result())
    assert len(calls) == 2
    assert slept[0] == 2.0
    assert first["fallback_reason"] == "rate_limited"
    assert first["explanation_label"] == "Template (rate limited, retrying later)"
    assert later["fallback_reason"] == "rate_limited"
    assert later["llm_calls_used"] == 0
    explainer.reset_llm_controls()


def test_llm_calls_are_spaced_by_at_least_one_second(monkeypatch):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)
    explainer.reset_llm_controls()
    clock = [10.0]
    call_times = []

    def fake_sleep(seconds):
        clock[0] += seconds

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "The evidence provides a tentative identity-graph signal."}}]}

    def fake_post(*args, **kwargs):
        call_times.append(clock[0])
        return Response()

    monkeypatch.setattr(explainer.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(explainer.time, "sleep", fake_sleep)
    monkeypatch.setattr(explainer.httpx, "post", fake_post)
    explainer.explain_result(_example_result())
    explainer.explain_result(_example_result())
    assert len(call_times) == 2
    assert call_times[1] - call_times[0] >= 1.0
    explainer.reset_llm_controls()


def test_unknown_provider_reports_provider_fallback(monkeypatch):
    from app.services.llm_explain import explainer

    monkeypatch.setenv("LLM_API_KEY", "sample-test-token-not-real")
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: pytest.fail("HTTP must not be called"))
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "template"
    assert result["fallback_reason"] == "unknown_provider"
    assert result["explanation_label"] == "Template (unknown provider)"


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [(401, "http_error_401"), (429, "rate_limited")],
)
def test_http_errors_report_status_fallback(monkeypatch, status_code, reason):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)
    monkeypatch.setattr(
        explainer.httpx,
        "post",
        lambda *args, **kwargs: _status_response(status_code),
    )
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "template"
    assert result["fallback_reason"] == reason
    expected_label = "Template (rate limited, retrying later)" if status_code == 429 else f"Template (HTTP error {status_code})"
    assert result["explanation_label"] == expected_label


def test_timeout_reports_timeout_fallback(monkeypatch):
    import httpx
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)

    def timeout(*args, **kwargs):
        raise httpx.TimeoutException("request timed out")

    monkeypatch.setattr(explainer.httpx, "post", timeout)
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "template"
    assert result["fallback_reason"] == "timeout"
    assert result["explanation_label"] == "Template (request timed out)"


def test_network_error_reports_network_fallback(monkeypatch):
    import httpx
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)

    def fail_network(*args, **kwargs):
        request = httpx.Request("POST", "https://provider.example.test")
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(explainer.httpx, "post", fail_network)
    result = explainer.explain_result(_example_result())
    assert result["fallback_reason"] == "network_error"
    assert result["explanation_label"] == "Template (network error)"


def test_malformed_response_reports_invalid_response(monkeypatch):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {}

    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: Response())
    result = explainer.explain_result(_example_result())
    assert result["fallback_reason"] == "invalid_response"
    assert result["explanation_label"] == "Template (invalid response)"


@pytest.mark.parametrize(
    "response_text",
    [
        "The evidence indicates 99 other accounts shared this infrastructure.",
        "Confidence remains tentative and PGP-SYN-FAKE1234 appears in the evidence.",
    ],
)
def test_ungrounded_number_or_identifier_is_rejected(monkeypatch, response_text):
    from app.services.llm_explain import explainer

    _configure_llm(monkeypatch)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": response_text}}]}

    monkeypatch.setattr(explainer.httpx, "post", lambda *args, **kwargs: Response())
    result = explainer.explain_result(_example_result())
    assert result["explanation_source"] == "template"
    assert result["fallback_reason"] == "validation_rejected"


def test_api_key_never_appears_in_explanation_or_logs(monkeypatch, caplog):
    import json
    from app.services.llm_explain import explainer

    caplog.set_level("INFO", logger=explainer.__name__)
    api_key = "sample-test-token-not-real"
    monkeypatch.setenv("LLM_API_KEY", api_key)
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "The evidence provides a tentative identity-graph signal."}}]}

    calls = {}

    def fake_post(*args, **kwargs):
        calls.update(kwargs)
        return Response()

    monkeypatch.setattr(explainer.httpx, "post", fake_post)
    result = explainer.explain_result(_example_result())
    assert "Bearer " + api_key == calls["headers"]["Authorization"]
    assert api_key not in json.dumps(result)
    assert api_key not in caplog.text
    assert "source=llm" in caplog.text
    assert "provider=groq" in caplog.text
    assert "model=openai/gpt-oss-20b" in caplog.text
    assert "latency_ms=" in caplog.text
