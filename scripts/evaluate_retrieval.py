"""Report retrieval quality and high-scoring false positives on the dataset.

Run from the repository root with: python scripts/evaluate_retrieval.py
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.data_loader import load_ground_truth, load_personas  # noqa: E402
from app.services.fusion.pipeline import score_pair  # noqa: E402

DECISION_THRESHOLD = 0.5
FUSED_THRESHOLDS = (0.5, 0.7, 0.8, 0.9)
PILLAR_CORROBORATION_THRESHOLD = 0.30


def classification_metrics(scored_pairs, actor_by_persona, threshold, corroborated=False):
    true_positives = 0
    false_positives = 0
    false_negatives = 0

    for (persona_id_a, persona_id_b), result in scored_pairs.items():
        is_twin = actor_by_persona[persona_id_a] == actor_by_persona[persona_id_b]
        pillar_matches = sum(
            score >= PILLAR_CORROBORATION_THRESHOLD
            for score in result["breakdown"].values()
        )
        predicted_match = result["confidence"] >= threshold and (
            not corroborated or pillar_matches >= 2
        )
        if predicted_match and is_twin:
            true_positives += 1
        elif predicted_match:
            false_positives += 1
        elif is_twin:
            false_negatives += 1

    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1, false_positives


def main() -> None:
    personas = load_personas()
    actors, labeled_pairs = load_ground_truth()
    actor_by_persona = {
        persona_id: actor.actor_id
        for actor in actors
        for persona_id in actor.persona_ids
    }
    actor_sizes = {actor.actor_id: len(actor.persona_ids) for actor in actors}
    missing = sorted(set(personas) - set(actor_by_persona))
    if missing:
        raise ValueError(f"Personas missing actor membership: {', '.join(missing)}")

    scored_pairs = {}
    for persona_id_a, persona_id_b in combinations(sorted(personas), 2):
        result = score_pair(personas[persona_id_a], personas[persona_id_b])
        scored_pairs[(persona_id_a, persona_id_b)] = result

    query_personas = [
        persona_id
        for persona_id in sorted(personas)
        if actor_sizes[actor_by_persona[persona_id]] > 1
    ]

    top_1 = 0
    top_3 = 0
    reciprocal_ranks = []
    for query_id in query_personas:
        ranked = []
        for candidate_id in personas:
            if candidate_id == query_id:
                continue
            pair_key = tuple(sorted((query_id, candidate_id)))
            ranked.append((scored_pairs[pair_key]["confidence"], candidate_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))

        relevant_ranks = [
            rank
            for rank, (_, candidate_id) in enumerate(ranked, start=1)
            if actor_by_persona[candidate_id] == actor_by_persona[query_id]
        ]
        if not relevant_ranks:
            continue
        first_relevant = relevant_ranks[0]
        top_1 += first_relevant == 1
        top_3 += first_relevant <= 3
        reciprocal_ranks.append(1.0 / first_relevant)

    positive_predictions = 0
    false_positives = []
    for (persona_id_a, persona_id_b), result in scored_pairs.items():
        is_twin = actor_by_persona[persona_id_a] == actor_by_persona[persona_id_b]
        if result["confidence"] >= DECISION_THRESHOLD:
            if is_twin:
                positive_predictions += 1
            else:
                false_positives.append((persona_id_a, persona_id_b, result))

    predicted_positive_pairs = positive_predictions + len(false_positives)
    precision = positive_predictions / predicted_positive_pairs if predicted_positive_pairs else 0.0
    mean_reciprocal_rank = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    scenario_by_pair = {
        tuple(sorted((pair.persona_a, pair.persona_b))): pair.scenario
        for pair in labeled_pairs
        if pair.same_actor
    }

    print(f"Personas: {len(personas)}")
    print(f"Unique persona pairs scored: {len(scored_pairs)}")
    print(f"Personas with at least one known twin: {len(reciprocal_ranks)}")
    print(f"Top-1 accuracy: {top_1 / len(reciprocal_ranks):.3f}")
    print(f"Top-3 accuracy: {top_3 / len(reciprocal_ranks):.3f}")
    print(f"Mean reciprocal rank: {mean_reciprocal_rank:.3f}")
    print(f"Non-twin pairs scoring >= {DECISION_THRESHOLD:.1f}: {len(false_positives)}")
    print(f"Precision at {DECISION_THRESHOLD:.1f}: {precision:.3f}")
    print()

    print("All-pair classification metrics by fused threshold")
    print(f"{'threshold':>10}{'precision':>12}{'recall':>10}{'F1':>10}{'false positives':>18}")
    for threshold in FUSED_THRESHOLDS:
        precision, recall, f1, false_positive_count = classification_metrics(
            scored_pairs, actor_by_persona, threshold
        )
        print(
            f"{threshold:>10.1f}{precision:>12.3f}{recall:>10.3f}"
            f"{f1:>10.3f}{false_positive_count:>18}"
        )

    print()
    print(
        "All-pair classification metrics with corroboration "
        f"(at least 2 pillars >= {PILLAR_CORROBORATION_THRESHOLD:.2f})"
    )
    print(f"{'threshold':>10}{'precision':>12}{'recall':>10}{'F1':>10}{'false positives':>18}")
    for threshold in FUSED_THRESHOLDS:
        precision, recall, f1, false_positive_count = classification_metrics(
            scored_pairs, actor_by_persona, threshold, corroborated=True
        )
        print(
            f"{threshold:>10.1f}{precision:>12.3f}{recall:>10.3f}"
            f"{f1:>10.3f}{false_positive_count:>18}"
        )

    print()
    print("True twin pairs lost by the corroborated rule")
    for threshold in FUSED_THRESHOLDS:
        lost = []
        for (persona_id_a, persona_id_b), result in scored_pairs.items():
            if actor_by_persona[persona_id_a] != actor_by_persona[persona_id_b]:
                continue
            pillar_matches = sum(
                score >= PILLAR_CORROBORATION_THRESHOLD
                for score in result["breakdown"].values()
            )
            if result["confidence"] < threshold or pillar_matches < 2:
                pair = (persona_id_a, persona_id_b)
                lost.append((pair, scenario_by_pair.get(pair, "unknown")))
        lost.sort()
        pairs_text = ", ".join(
            f"{persona_id_a}-{persona_id_b} ({scenario})"
            for (persona_id_a, persona_id_b), scenario in lost
        ) or "none"
        print(f"threshold {threshold:.1f}: {pairs_text}")

    print()
    print("10 highest-scoring false-positive pairs (non-twins, score >= 0.5)")
    print(f"{'pair':<17}{'confidence':>12}{'identity':>12}{'infrastructure':>17}{'stylometry':>13}")

    false_positives.sort(
        key=lambda item: (-item[2]["confidence"], item[0], item[1])
    )
    for persona_id_a, persona_id_b, result in false_positives[:10]:
        breakdown = result["breakdown"]
        print(
            f"{persona_id_a}-{persona_id_b:<12}"
            f"{result['confidence']:>12.3f}"
            f"{breakdown['identity_graph']:>12.3f}"
            f"{breakdown['infrastructure']:>17.3f}"
            f"{breakdown['stylometry']:>13.3f}"
        )


if __name__ == "__main__":
    main()
