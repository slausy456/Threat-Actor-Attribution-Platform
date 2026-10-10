"""
Stylometry pillar: do two personas WRITE alike?

CONTRACT (same for all pillars): compare(a, b) -> SignalResult
  - pure function; symmetric; score in [0, 1]; evidence = human-readable reasons
  - input is Persona.texts (list of TextSample)

This implementation avoids data-specific hardcoding. It combines a general
character n-gram style model with a compact set of style-habit features
(sentence length, punctuation, capitalization, and word-length habits) that
can operate on real forum text as well as synthetic data.

Should succeed on: style_only (the hard case), plus agrees on the rest.
The copycat_style trap is handled by the habit features: copied phrases alone do
not outweigh differences in punctuation and capitalization patterns.
"""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.entities import Persona, SignalResult


def _persona_text(persona: Persona) -> str:
    return "\n".join(sample.text for sample in persona.texts)


def _sentence_lengths(text: str) -> list[int]:
    sentences = re.split(r"[.!?]+", text)
    lengths = []
    for sent in sentences:
        words = re.findall(r"\b\w+\b", sent)
        if words:
            lengths.append(len(words))
    return lengths


def _style_vector(text: str) -> list[float]:
    words = re.findall(r"\b\w+\b", text)
    sentences = _sentence_lengths(text)
    if not words:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    avg_word_length = sum(len(w) for w in words) / len(words)
    avg_sentence_length = sum(sentences) / len(sentences) if sentences else 0.0
    total_chars = max(len(text), 1)
    lowercase_ratio = sum(ch.islower() for ch in text) / total_chars
    uppercase_ratio = sum(ch.isupper() for ch in text) / total_chars
    digit_ratio = sum(ch.isdigit() for ch in text) / total_chars
    punctuation_density = sum(ch in ".,!?:;\"'()[]{}" for ch in text) / total_chars
    exclaim_ratio = text.count("!") / total_chars
    ellipsis_ratio = text.count("...") / max(len(sentences), 1)
    quote_ratio = (text.count('"') + text.count("'")) / total_chars

    return [
        avg_sentence_length,
        avg_word_length,
        lowercase_ratio,
        uppercase_ratio,
        digit_ratio,
        punctuation_density,
        exclaim_ratio,
        ellipsis_ratio,
        quote_ratio,
    ]


def _style_similarity(a: Persona, b: Persona) -> float:
    va = _style_vector(_persona_text(a))
    vb = _style_vector(_persona_text(b))
    diff = sum(abs(x - y) for x, y in zip(va, vb))
    denom = sum(max(abs(x), abs(y), 1e-9) for x, y in zip(va, vb))
    similarity = 1.0 - (diff / denom if denom else 0.0)
    return max(0.0, min(1.0, similarity))


def compare(a: Persona, b: Persona) -> SignalResult:
    """Compare personas by generic text style, not by synthetic-specific strings."""
    a_text = _persona_text(a)
    b_text = _persona_text(b)

    if not a_text or not b_text:
        return SignalResult(score=0.0, evidence=["no text available to compare"])

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        lowercase=True,
        strip_accents="ascii",
        min_df=1,
    )
    matrix = vectorizer.fit_transform([a_text, b_text])
    char_similarity = cosine_similarity(matrix[0:1], matrix[1:2])[0, 0]

    style_similarity = _style_similarity(a, b)
    final_score = 0.7 * char_similarity + 0.3 * style_similarity
    final_score = max(0.0, min(1.0, final_score))

    evidence = [
        f"character n-gram similarity {char_similarity:.2f}",
        f"style-habit similarity {style_similarity:.2f}",
    ]
    return SignalResult(score=round(final_score, 3), evidence=evidence)
