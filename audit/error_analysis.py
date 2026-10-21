"""Detailed error analysis for the bundled synthetic persona dataset.

Run from the repository root:
    python audit/error_analysis.py

Confidence is produced by the same runtime ``score_pair`` path as
``audit/accuracy_check.py``. The full 72-persona pair space is evaluated;
ground-truth scenario summaries use only the labelled pairs listed in
``ground_truth.json``. Labels are consulted only after scoring.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    from app.data_loader import load_ground_truth, load_personas
    from app.services.fusion.pipeline import score_pair
    from app.services.stylometry.matcher import (
        _persona_text,
        _style_similarity,
        TfidfVectorizer,
        cosine_similarity,
    )
except ModuleNotFoundError as error:
    if error.name == "sklearn":
        raise SystemExit(
            "Cannot run error analysis: scikit-learn is required by the runtime "
            "stylometry scorer but is not installed."
        ) from error
    raise


def style_components(a, b) -> tuple[float, float]:
    """Return the runtime matcher’s (style habits, character n-gram) scores."""
    a_text = _persona_text(a)
    b_text = _persona_text(b)
    if not a_text or not b_text:
        return 0.0, 0.0
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        lowercase=True,
        strip_accents="ascii",
        min_df=1,
    )
    matrix = vectorizer.fit_transform([a_text, b_text])
    char_ngram = float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])
    style_habits = float(_style_similarity(a, b))
    return style_habits, char_ngram


def describe(values: list[float]) -> str:
    if not values:
        return "n=0 min=NA median=NA max=NA average=NA"
    return (
        f"n={len(values)} min={min(values):.3f} median={median(values):.3f} "
        f"max={max(values):.3f} average={mean(values):.3f}"
    )


def normalized_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in (
            " ".join(piece.casefold().split())
            for piece in re.split(r"[.!?]+", text)
        )
        if sentence
    ]


def main() -> None:
    personas = load_personas()
    _, labelled_pairs = load_ground_truth()
    actor_by_persona = {}
    actors, _ = load_ground_truth()
    for actor in actors:
        for persona_id in actor.persona_ids:
            actor_by_persona[persona_id] = actor.actor_id

    scored: dict[tuple[str, str], dict] = {}
    features: dict[tuple[str, str], tuple[float, float]] = {}
    same_style_habits: list[float] = []
    different_style_habits: list[float] = []
    same_char_ngrams: list[float] = []
    different_char_ngrams: list[float] = []

    for a_id, b_id in combinations(sorted(personas), 2):
        a, b = personas[a_id], personas[b_id]
        result = score_pair(a, b)
        key = (a_id, b_id)
        scored[key] = result
        habit_score, ngram_score = style_components(a, b)
        features[key] = (habit_score, ngram_score)
        is_same = actor_by_persona[a_id] == actor_by_persona[b_id]
        (same_style_habits if is_same else different_style_habits).append(habit_score)
        (same_char_ngrams if is_same else different_char_ngrams).append(ngram_score)

    print("1. Same-actor pairs missed at confidence >= 0.90")
    missed = []
    for pair in labelled_pairs:
        if not pair.same_actor:
            continue
        key = tuple(sorted((pair.persona_a, pair.persona_b)))
        result = scored[key]
        if result["confidence"] < 0.90:
            missed.append((key, pair, result))
    if not missed:
        print("  None.")
    for (a_id, b_id), pair, result in sorted(missed):
        breakdown = result["breakdown"]
        print(
            f"  {a_id}-{b_id} scenario={pair.scenario} "
            f"identity={breakdown['identity_graph']:.3f} "
            f"infrastructure={breakdown['infrastructure']:.3f} "
            f"stylometry={breakdown['stylometry']:.3f} "
            f"confidence={result['confidence']:.3f}"
        )
    print(f"  Total missed labelled same-actor pairs: {len(missed)}")

    print("\n2. Ground-truth scenario summaries (labelled pairs only)")
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for pair in labelled_pairs:
        key = tuple(sorted((pair.persona_a, pair.persona_b)))
        by_scenario[pair.scenario].append(scored[key])
    print("  scenario                 pairs mean_conf >=0.90 >=0.70")
    for scenario in sorted(by_scenario):
        rows = by_scenario[scenario]
        confidences = [row["confidence"] for row in rows]
        print(
            f"  {scenario:<24} {len(rows):>5} {mean(confidences):>9.3f} "
            f"{sum(value >= 0.90 for value in confidences):>7} "
            f"{sum(value >= 0.70 for value in confidences):>6}"
        )

    print("\n3. Different-actor pairs with confidence >= 0.70")
    categories = Counter()
    qualifying = 0
    for key, result in scored.items():
        if actor_by_persona[key[0]] == actor_by_persona[key[1]]:
            continue
        if result["confidence"] < 0.70:
            continue
        qualifying += 1
        breakdown = result["breakdown"]
        evidence = result.get("evidence", {})
        identity_evidence = evidence.get("identity_graph", [])
        infra_evidence = evidence.get("infrastructure", [])
        style_score = breakdown["stylometry"]
        if breakdown["identity_graph"] == 0 and breakdown["infrastructure"] == 0:
            category = "stylometry-only"
        elif style_score > 0 and any("banner" in item for item in infra_evidence):
            category = "banner+style"
        elif style_score > 0 and any(
            "handle" in item.lower() for item in identity_evidence
        ):
            category = "handle+style"
        else:
            category = "other"
        categories[category] += 1
    print(f"  qualifying false positives: {qualifying}")
    for category in ("stylometry-only", "banner+style", "handle+style", "other"):
        print(f"  {category}: {categories[category]}")
    print("  Categories are mutually exclusive; banner+style takes priority over handle+style.")

    print("\n4. Stylometry component distributions (all possible persona pairs)")
    print(f"  Same-actor style-habit similarity: {describe(same_style_habits)}")
    print(f"  Different-actor style-habit similarity: {describe(different_style_habits)}")
    print(f"  Same-actor character n-gram similarity: {describe(same_char_ngrams)}")
    print(f"  Different-actor character n-gram similarity: {describe(different_char_ngrams)}")

    print("\n5. Repeated template sentences")
    sentence_personas: dict[str, set[str]] = defaultdict(set)
    sentence_occurrences: Counter = Counter()
    sentence_sets_by_persona: dict[str, list[set[str]]] = defaultdict(list)
    for persona_id, persona in personas.items():
        for post in persona.texts:
            sentences = normalized_sentences(post.text)
            sentence_sets_by_persona[persona_id].append(set(sentences))
            for sentence in sentences:
                sentence_occurrences[sentence] += 1
                sentence_personas[sentence].add(persona_id)

    personas_with_common_sentence = 0
    for post_sentence_sets in sentence_sets_by_persona.values():
        if post_sentence_sets and set.intersection(*post_sentence_sets):
            personas_with_common_sentence += 1
    print(
        f"  Personas with at least one identical sentence in every post: "
        f"{personas_with_common_sentence}/{len(personas)}"
    )
    print("  Top 10 sentences by total post occurrences (persona count shown separately):")
    for sentence, occurrences in sorted(
        sentence_occurrences.items(), key=lambda item: (-item[1], item[0])
    )[:10]:
        print(
            f"  occurrences={occurrences:>4} personas={len(sentence_personas[sentence]):>2} "
            f"{sentence}"
        )

    print("\nSummary: see counts above; all confidence values come from score_pair.")


if __name__ == "__main__":
    main()
