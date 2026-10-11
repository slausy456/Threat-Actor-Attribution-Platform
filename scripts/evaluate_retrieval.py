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


def main() -> None:
    personas = load_personas()
    actors, _ = load_ground_truth()
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

    print(f"Personas: {len(personas)}")
    print(f"Unique persona pairs scored: {len(scored_pairs)}")
    print(f"Personas with at least one known twin: {len(reciprocal_ranks)}")
    print(f"Top-1 accuracy: {top_1 / len(reciprocal_ranks):.3f}")
    print(f"Top-3 accuracy: {top_3 / len(reciprocal_ranks):.3f}")
    print(f"Mean reciprocal rank: {mean_reciprocal_rank:.3f}")
    print(f"Non-twin pairs scoring >= {DECISION_THRESHOLD:.1f}: {len(false_positives)}")
    print(f"Precision at {DECISION_THRESHOLD:.1f}: {precision:.3f}")
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
