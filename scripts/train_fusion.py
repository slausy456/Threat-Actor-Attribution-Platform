"""Train the fusion model on the synthetic labelled pairs and save the learned weights."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import GroupKFold

from app.data_loader import load_ground_truth, load_personas
from app.services.identity_graph.matcher import compare as compare_identity
from app.services.infrastructure_scan.matcher import compare as compare_infra
from app.services.stylometry.matcher import compare as compare_style

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_PATH = ROOT / "backend" / "app" / "services" / "fusion" / "weights.json"
MODEL_C = 10


def build_dataset():
    personas = load_personas()
    actors, pairs = load_ground_truth()
    actor_of = {persona_id: actor.actor_id for actor in actors for persona_id in actor.persona_ids}

    X, y, groups = [], [], []
    for pair in pairs:
        a = personas[pair.persona_a]
        b = personas[pair.persona_b]
        X.append([
            compare_identity(a, b).score,
            compare_infra(a, b).score,
            compare_style(a, b).score,
        ])
        y.append(int(pair.same_actor))
        groups.append(actor_of[pair.persona_a])
    return X, y, groups


def select_threshold(labels, probabilities):
    candidates = sorted({0.0, *probabilities, 1.0})
    return max(
        candidates,
        key=lambda threshold: (
            f1_score(labels, [p >= threshold for p in probabilities], zero_division=0),
            recall_score(labels, [p >= threshold for p in probabilities], zero_division=0),
            threshold,
        ),
    )


def cross_validated_probabilities(X, y, groups, n_splits):
    probabilities = [0.0] * len(y)
    splitter = GroupKFold(n_splits=n_splits)
    for train_idx, test_idx in splitter.split(X, y, groups):
        model = LogisticRegression(max_iter=2000, C=MODEL_C)
        model.fit([X[i] for i in train_idx], [y[i] for i in train_idx])
        fold_probabilities = model.predict_proba([X[i] for i in test_idx])[:, 1]
        for index, probability in zip(test_idx, fold_probabilities):
            probabilities[index] = float(probability)
    return probabilities


def calibrate_intercept(model, threshold):
    threshold = min(max(float(threshold), 1e-6), 1 - 1e-6)
    model.intercept_[0] += math.log((1 - threshold) / threshold)
    return model


def main() -> None:
    X, y, groups = build_dataset()
    n_splits = min(5, len(set(groups)))
    outer = GroupKFold(n_splits=n_splits)
    cv_predictions = [0] * len(y)
    for train_idx, test_idx in outer.split(X, y, groups):
        fold_X = [X[i] for i in train_idx]
        fold_y = [y[i] for i in train_idx]
        fold_groups = [groups[i] for i in train_idx]
        inner_splits = min(4, len(set(fold_groups)))
        inner_probabilities = cross_validated_probabilities(
            fold_X, fold_y, fold_groups, inner_splits
        )
        threshold = select_threshold(fold_y, inner_probabilities)
        model = LogisticRegression(max_iter=2000, C=MODEL_C)
        model.fit(fold_X, fold_y)
        calibrate_intercept(model, threshold)
        predictions = model.predict([X[i] for i in test_idx])
        for index, prediction in zip(test_idx, predictions):
            cv_predictions[index] = int(prediction)

    final_oof = cross_validated_probabilities(X, y, groups, n_splits)
    threshold = max(1e-6, select_threshold(y, final_oof) * 0.9)
    model = LogisticRegression(max_iter=2000, C=MODEL_C)
    model.fit(X, y)
    calibrate_intercept(model, threshold)
    in_sample = model.predict(X)

    print("Nested GroupKFold precision/recall/F1:")
    print(
        precision_score(y, cv_predictions, zero_division=0),
        recall_score(y, cv_predictions, zero_division=0),
        f1_score(y, cv_predictions, zero_division=0),
    )
    print("In-sample precision/recall/F1:")
    print(
        precision_score(y, in_sample, zero_division=0),
        recall_score(y, in_sample, zero_division=0),
        f1_score(y, in_sample, zero_division=0),
    )

    weights = {
        "intercept": float(model.intercept_[0]),
        "identity_graph": float(model.coef_[0][0]),
        "infrastructure": float(model.coef_[0][1]),
        "stylometry": float(model.coef_[0][2]),
        "oof_decision_threshold": float(threshold),
    }
    WEIGHTS_PATH.write_text(json.dumps(weights, indent=2) + "\n")
    print(f"Saved fusion weights to {WEIGHTS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
