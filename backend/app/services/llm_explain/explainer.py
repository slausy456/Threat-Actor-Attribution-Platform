"""Grounded, uncertainty-aware explanations for fusion results."""
from __future__ import annotations

import json
import os
import re

import httpx

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
    level = "low" if confidence < 0.35 else "moderate" if confidence < 0.7 else "high"
    breakdown = result.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    scores = {key: _score(breakdown.get(key)) for key in PILLAR_NAMES}
    evidence = _evidence_map(result)
    strongest = sorted(scores, key=scores.get, reverse=True)
    lead = strongest[0]
    lead_name = PILLAR_NAMES[lead]
    lead_evidence = evidence.get(lead, [])

    sentences = [
        f"Overall confidence is {level} ({confidence:.2f}), so this is a tentative assessment rather than a calibrated probability."
    ]
    if scores[lead] >= 0.4 and lead_evidence:
        quoted = "; ".join(f'“{item[:180]}”' for item in lead_evidence[:2])
        sentences.append(
            f"The clearest signal is {lead_name} ({scores[lead]:.2f}), supported by {quoted}."
        )
    elif lead_evidence:
        sentences.append(
            f"The strongest available signal is {lead_name} ({scores[lead]:.2f}); its evidence is limited to “{lead_evidence[0][:180]}”."
        )
    else:
        sentences.append(
            f"The strongest available signal is {lead_name} ({scores[lead]:.2f}), but no supporting evidence was provided for it."
        )

    weakest = min(scores, key=scores.get)
    weak_name = PILLAR_NAMES[weakest]
    sentences.append(
        f"The {weak_name} signal is weak ({scores[weakest]:.2f}), which limits what can be concluded."
    )
    sentences.append("Treat this as a lead for human review, not proof of attribution.")
    return " ".join(sentences)


def _identifiers(text: str) -> set[str]:
    return {match.group(0).lower() for pattern in IDENTIFIER_PATTERNS for match in pattern.finditer(text)}


def _valid_llm_text(text: str, evidence: dict[str, list[str]]) -> bool:
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]
    if not 20 <= len(text) <= 1200 or not 2 <= len(sentences) <= 4:
        return False
    if not UNCERTAINTY_TERMS.search(text):
        return False
    if not re.search(r"human review|lead|not proof", text, re.IGNORECASE):
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
                "Write 2 to 4 plain sentences for an investigator. Explain confidence and which "
                "signals support it, identify weak or missing evidence, and say this is a lead "
                "for human review, not proof. Use uncertainty. Treat the supplied JSON as the "
                "complete factual record: do not invent, infer, or add identifiers, events, "
                "relationships, or other facts absent from it. Never state identity as certain."
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
    return _llm_explanation(result, evidence) or _template(result)