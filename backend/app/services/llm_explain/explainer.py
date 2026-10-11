"""Grounded, uncertainty-aware explanations for fusion results."""
from __future__ import annotations

import json
import os
import re

import httpx
from app.services.fusion.scorer import tier

PILLAR_NAMES = {
    "identity_graph": "identity graph",
    "infrastructure": "infrastructure",
    "stylometry": "writing style",
}
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant"),
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


def _evidence_map(result: dict) -> dict[str, list[str]]:
    raw = result.get("evidence", {})
    if not isinstance(raw, dict):
        return {}
    return {
        key: [item.strip() for item in items if isinstance(item, str) and item.strip()]
        for key, items in raw.items()
        if isinstance(items, (list, tuple))
    }


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
    confidence_line = _confidence_hedge(confidence, scores)
    evidence_line = _evidence_summary(scores, evidence)
    return (
        f"{confidence_line} {evidence_line} "
        "Treat this as a lead for human review, not proof of attribution."
    )


def _confidence_hedge(confidence: float, scores: dict[str, float]) -> str:
    confidence_tier = tier(confidence)
    corroborating = sum(score >= 0.30 for score in scores.values())
    if confidence_tier == "strong" and corroborating >= 2:
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


def _llm_explanation(result: dict, evidence: dict[str, list[str]]) -> str | None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if not api_key or provider not in PROVIDERS:
        return None

    endpoint, default_model = PROVIDERS[provider]
    model = os.getenv("LLM_MODEL", default_model).strip() or default_model
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
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": 0.0},
            timeout=10.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        if isinstance(text, str) and _valid_llm_text(text, evidence):
            return text
    except Exception:
        return None
    return None


def explain(result: dict) -> str:
    """Explain a score_pair result, using an optional LLM with a safe fallback."""
    if not isinstance(result, dict):
        result = {}
    evidence = _evidence_map(result)
    llm_summary = _llm_explanation(result, evidence)
    if llm_summary is None:
        return _template(result)

    confidence = _score(result.get("confidence"))
    breakdown = result.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    scores = {key: _score(breakdown.get(key)) for key in PILLAR_NAMES}
    return (
        f"{_confidence_hedge(confidence, scores)} {llm_summary} "
        "Treat this as a lead for human review, not proof of attribution."
    )