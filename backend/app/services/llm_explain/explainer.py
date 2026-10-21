"""Grounded, uncertainty-aware explanations for fusion results."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from app.services.fusion.scorer import MIN_PILLAR_SCORE, tier

PILLAR_NAMES = {
    "identity_graph": "identity graph",
    "infrastructure": "infrastructure",
    "stylometry": "writing style",
}
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-20b"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
}
IDENTIFIER_PATTERNS = (
    re.compile(r"\bPGP(?:-SYN)?-[A-Z0-9-]{4,}\b", re.IGNORECASE),
    re.compile(r"\bbc1[a-z0-9]{10,}\b", re.IGNORECASE),
    re.compile(r"\b0x[a-f0-9]{16,}\b", re.IGNORECASE),
    re.compile(r"\b[a-f0-9]{16,}\b", re.IGNORECASE),
)
UNCERTAINTY_TERMS = re.compile(
    r"\b(uncertain|uncertainty|tentative|possible|possibly|may|might|suggests?|limited|confidence|likely)\b",
    re.IGNORECASE,
)
NUMBERS = re.compile(r"\b\d+(?:\.\d+)?\b")
FALLBACK_LABELS = {
    "no_key": "no API key",
    "unknown_provider": "unknown provider",
    "timeout": "request timed out",
    "network_error": "network error",
    "validation_rejected": "response failed validation",
    "invalid_response": "invalid response",
    "rate_limited": "rate limited, retrying later",
    "call_budget_exhausted": "session call budget exhausted",
}
logger = logging.getLogger(__name__)
_LLM_CALL_LOCK = threading.Lock()
_LAST_LLM_CALL_AT = 0.0
_CIRCUIT_OPEN_UNTIL = 0.0
MIN_SECONDS_BETWEEN_CALLS = 1.0
CIRCUIT_BREAK_SECONDS = 60.0


def configured_model() -> str:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    default_model = PROVIDERS.get(provider, (None, "unknown"))[1]
    return os.getenv("LLM_MODEL", default_model).strip() or default_model


def reset_llm_controls() -> None:
    """Reset process limiter state for isolated tests."""
    global _LAST_LLM_CALL_AT, _CIRCUIT_OPEN_UNTIL
    with _LLM_CALL_LOCK:
        _LAST_LLM_CALL_AT = 0.0
        _CIRCUIT_OPEN_UNTIL = 0.0


def _evidence_map(result: dict) -> dict[str, list[str]]:
    raw = result.get("evidence", {})
    if not isinstance(raw, dict):
        return {}
    normalized = {}
    for key, items in raw.items():
        if not isinstance(items, (list, tuple)):
            continue
        descriptions = []
        for item in items:
            if isinstance(item, str) and item.strip():
                descriptions.append(item.strip())
            elif isinstance(item, dict) and isinstance(item.get("description"), str):
                descriptions.append(item["description"].strip())
        normalized[key] = descriptions
    return normalized


def _score(value) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _template(result: dict) -> str:
    confidence = _score(result.get("confidence"))
    breakdown = result.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    scores = {key: _score(breakdown.get(key)) for key in PILLAR_NAMES}
    evidence = _evidence_map(result)
    confidence_line = _confidence_hedge(
        confidence, scores, single_signal=bool(result.get("single_signal", False))
    )
    evidence_line = _evidence_summary(scores, evidence)
    return (
        f"{confidence_line} {evidence_line} "
        "Treat this as a lead for human review, not proof of attribution."
    )


def _confidence_hedge(
    confidence: float, scores: dict[str, float], *, single_signal: bool = False
) -> str:
    confidence_tier = tier(confidence, single_signal=single_signal)
    corroborating = sum(score >= MIN_PILLAR_SCORE for score in scores.values())
    if confidence_tier == "lead":
        hedge = "fewer than two pillars corroborate this lead, so the result is tentative"
    elif confidence_tier == "strong" and corroborating >= 2:
        hedge = "several independent signals agree; still a lead for human review"
    elif confidence_tier == "weak":
        hedge = "this is tentative"
    elif confidence_tier in {"strong", "moderate"} and corroborating == 1:
        hedge = "this rests on a single signal"
    elif confidence_tier == "moderate" and corroborating >= 2:
        hedge = "multiple signals contribute, but the evidence is not conclusive"
    else:
        hedge = "corroboration is limited, so the assessment remains tentative"
    return f"Confidence is {confidence:.3f} ({confidence_tier} tier); {hedge}."


def _evidence_summary(scores: dict[str, float], evidence: dict[str, list[str]]) -> str:
    domains = {
        "identity_graph": "identity",
        "infrastructure": "infrastructure",
        "stylometry": "writing-style",
    }
    parts = []
    for pillar, label in PILLAR_NAMES.items():
        score = scores[pillar]
        details = evidence.get(pillar, [])
        if score == 0 and not details:
            parts.append(f"no shared {domains[pillar]} evidence was found")
            continue

        quoted = "; ".join(f'“{item[:180]}”' for item in details[:2])
        if 0 < score < 0.30:
            description = f"{label} evidence is weak ({score:.3f})"
        else:
            description = f"{label} score is {score:.3f}"
        if quoted:
            description += f": {quoted}"
        elif score == 0:
            description += "; no evidence details were recorded"
        else:
            description += "; no evidence details were recorded"
        parts.append(description)
    return "; ".join(parts) + "."


def _identifiers(text: str) -> set[str]:
    return {match.group(0).lower() for pattern in IDENTIFIER_PATTERNS for match in pattern.finditer(text)}


def _valid_llm_text(text: str, evidence: dict[str, list[str]]) -> bool:
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]
    if not 20 <= len(text) <= 700 or len(sentences) != 1:
        return False
    if re.search(r"same actor|same person|definitely|certainly", text, re.IGNORECASE):
        return False
    source = " ".join(item for items in evidence.values() for item in items)
    return _identifiers(text).issubset(_identifiers(source))


def _numeric_claims_grounded(text: str, result: dict, evidence: dict[str, list[str]]) -> bool:
    source = " ".join(item for items in evidence.values() for item in items)
    source += " " + json.dumps(
        {
            "confidence": result.get("confidence"),
            "breakdown": result.get("breakdown", {}),
        },
        ensure_ascii=True,
    )
    return set(NUMBERS.findall(text)) <= set(NUMBERS.findall(source))


def _retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _request_llm_explanation(
    result: dict,
    evidence: dict[str, list[str]],
    *,
    endpoint: str,
    model: str,
    api_key: str,
    max_calls: int = 2,
) -> tuple[str | None, str | None, int]:
    global _LAST_LLM_CALL_AT, _CIRCUIT_OPEN_UNTIL
    prompt_data = {
        "confidence": result.get("confidence"),
        "breakdown": result.get("breakdown", {}),
        "evidence": evidence,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Write exactly one concise sentence describing only the supplied pillar scores "
                "and evidence. Do not make an attribution conclusion. Treat the supplied JSON as "
                "the complete factual record: do not invent, infer, or add identifiers, events, "
                "relationships, or other facts absent from it."
            ),
        },
        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=True)},
    ]
    calls = 0
    rate_limit_seen = False
    with _LLM_CALL_LOCK:
        if time.monotonic() < _CIRCUIT_OPEN_UNTIL:
            return None, "rate_limited", calls
        for attempt in range(min(2, max(1, max_calls))):
            wait_for_slot = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _LAST_LLM_CALL_AT)
            if _LAST_LLM_CALL_AT and wait_for_slot > 0:
                time.sleep(wait_for_slot)
            _LAST_LLM_CALL_AT = time.monotonic()
            calls += 1
            try:
                response = httpx.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": messages, "temperature": 0.0},
                    timeout=10.0,
                )
                response.raise_for_status()
            except httpx.TimeoutException:
                if rate_limit_seen:
                    _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
                    return None, "rate_limited", calls
                return None, "timeout", calls
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    if attempt == 0 and calls < max_calls:
                        rate_limit_seen = True
                        retry_after = _retry_after_seconds(error.response.headers.get("Retry-After"))
                        if retry_after:
                            time.sleep(retry_after)
                        continue
                    _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
                    return None, "rate_limited", calls
                if rate_limit_seen:
                    _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
                    return None, "rate_limited", calls
                return None, f"http_error_{error.response.status_code}", calls
            except httpx.RequestError:
                if rate_limit_seen:
                    _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
                    return None, "rate_limited", calls
                return None, "network_error", calls
            if rate_limit_seen:
                _CIRCUIT_OPEN_UNTIL = time.monotonic() + CIRCUIT_BREAK_SECONDS
            break
        else:
            return None, "rate_limited", calls

    try:
        text = response.json()["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            return None, "invalid_response", calls
        text = text.strip()
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None, "invalid_response", calls

    if (
        api_key in text
        or not _valid_llm_text(text, evidence)
        or not _numeric_claims_grounded(text, result, evidence)
    ):
        return None, "validation_rejected", calls
    return text, None, calls


def explain_result(
    result: dict,
    *,
    allow_llm: bool = True,
    disabled_reason: str = "llm_disabled",
    max_calls: int = 2,
) -> dict[str, str | None | int]:
    """Return an explanation with its source and a human-readable source label."""
    if not isinstance(result, dict):
        result = {}
    evidence = _evidence_map(result)
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = configured_model()
    started_at = time.perf_counter()

    llm_summary = None
    calls_used = 0
    if not allow_llm:
        fallback_reason = disabled_reason
    elif not api_key:
        fallback_reason = "no_key"
    elif provider not in PROVIDERS:
        fallback_reason = "unknown_provider"
    else:
        endpoint, _ = PROVIDERS[provider]
        llm_summary, fallback_reason, calls_used = _request_llm_explanation(
            result,
            evidence,
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            max_calls=max_calls,
        )

    if llm_summary is None:
        explanation = _template(result)
        source = "template"
        reason_label = FALLBACK_LABELS.get(
            fallback_reason,
            f"HTTP error {fallback_reason.removeprefix('http_error_')}",
        )
        label = f"Template ({reason_label})"
    else:
        confidence = _score(result.get("confidence"))
        breakdown = result.get("breakdown", {})
        if not isinstance(breakdown, dict):
            breakdown = {}
        scores = {key: _score(breakdown.get(key)) for key in PILLAR_NAMES}
        explanation = (
            f"{_confidence_hedge(confidence, scores, single_signal=bool(result.get('single_signal', False)))} {llm_summary} "
            "Treat this as a lead for human review, not proof of attribution."
        )
        source = "llm"
        fallback_reason = None
        label = f"AI-generated ({model})"

    logger.info(
        "explanation source=%s reason=%s provider=%s model=%s latency_ms=%d key_length=%d",
        source,
        fallback_reason or "none",
        provider,
        model,
        round((time.perf_counter() - started_at) * 1000),
        len(api_key),
    )
    return {
        "explanation": explanation,
        "explanation_source": source,
        "fallback_reason": fallback_reason,
        "explanation_label": label,
        "llm_calls_used": calls_used,
    }


def explain(result: dict) -> str:
    """Explain a score_pair result, using an optional LLM with a safe fallback."""
    return str(explain_result(result)["explanation"])
