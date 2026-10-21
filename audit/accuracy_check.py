"""Exhaustive synthetic-pair evaluation of the repository's runtime scorer.

Run from the repository root with:
    python audit/accuracy_check.py

Ground truth is read here solely to evaluate outputs; score_pair receives only
persona records. Writes JSON results beside this script.
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_loader import load_ground_truth, load_personas  # noqa: E402
from app.services.fusion.pipeline import score_pair  # noqa: E402


def metrics(rows, threshold):
    tp = fp = tn = fn = 0
    for row in rows:
        predicted = row["confidence"] >= threshold
        actual = row["same_actor"]
        if predicted and actual:
            tp += 1
        elif predicted:
            fp += 1
        elif actual:
            fn += 1
        else:
            tn += 1
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def main():
    personas = load_personas()
    actors, labelled_pairs = load_ground_truth()
    actor_by_persona = {
        persona_id: actor.actor_id
        for actor in actors
        for persona_id in actor.persona_ids
    }
    rows = []
    for a_id, b_id in combinations(sorted(personas), 2):
        result = score_pair(personas[a_id], personas[b_id])
        rows.append({
            "a": a_id,
            "b": b_id,
            "same_actor": actor_by_persona[a_id] == actor_by_persona[b_id],
            **result,
        })

    calibration = []
    for index in range(10):
        low, high = index / 10, (index + 1) / 10
        bucket = [
            row for row in rows
            if low <= row["confidence"] < high
            or (index == 9 and row["confidence"] == 1.0)
        ]
        calibration.append({
            "bin": f"{low:.1f}-{high:.1f}",
            "count": len(bucket),
            "mean_confidence": (
                sum(row["confidence"] for row in bucket) / len(bucket)
                if bucket else None
            ),
            "actual_same_actor_fraction": (
                sum(row["same_actor"] for row in bucket) / len(bucket)
                if bucket else None
            ),
        })
    false_positives = sorted(
        (row for row in rows if not row["same_actor"]),
        key=lambda row: (-row["confidence"], row["a"], row["b"]),
    )[:10]
    scored_by_pair = {(row["a"], row["b"]): row for row in rows}
    scenario_rows = {}
    for pair in labelled_pairs:
        key = tuple(sorted((pair.persona_a, pair.persona_b)))
        scenario_rows.setdefault(pair.scenario, []).append(scored_by_pair[key])
    scenario_metrics = []
    for scenario, scenario_pairs in sorted(scenario_rows.items()):
        confidences = [row["confidence"] for row in scenario_pairs]
        scenario_metrics.append({
            "scenario": scenario,
            "pair_count": len(scenario_pairs),
            "mean_confidence": sum(confidences) / len(confidences),
            "count_ge_0.90": sum(value >= 0.90 for value in confidences),
            "count_ge_0.70": sum(value >= 0.70 for value in confidences),
        })
    output = {
        "persona_count": len(personas),
        "pair_count": len(rows),
        "positive_pairs": sum(row["same_actor"] for row in rows),
        "negative_pairs": sum(not row["same_actor"] for row in rows),
        "metrics": [metrics(rows, threshold) for threshold in (0.90, 0.70)],
        "scenario_metrics": scenario_metrics,
        "calibration": calibration,
        "highest_scoring_false_positives": false_positives,
    }
    target = Path(__file__).with_name("accuracy_results.json")
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    print("\nScenario metrics: scenario | pairs | mean confidence | >=0.90 | >=0.70")
    for row in scenario_metrics:
        print(
            f"{row['scenario']} | {row['pair_count']} | "
            f"{row['mean_confidence']:.3f} | {row['count_ge_0.90']} | "
            f"{row['count_ge_0.70']}"
        )


if __name__ == "__main__":
    main()
