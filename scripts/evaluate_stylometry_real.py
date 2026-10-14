"""Evaluate stylometry on locally supplied VeriDark pair splits only.

Expected local layout (files are not downloaded by this script):
    data/veridark/
      train/<one JSON file per pair>
      val/<one JSON file per pair>
      test/<one JSON file per pair>

Run from the repository root with: python scripts/evaluate_stylometry_real.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data" / "veridark"
sys.path.insert(0, str(ROOT / "backend"))

from app.models.entities import Persona, TextSample  # noqa: E402
from app.services.stylometry.matcher import compare  # noqa: E402

SPLITS = ("train", "val", "test")
FIXED_TIMESTAMP = "2000-01-01T00:00:00"
EXPECTED_LAYOUT = """Expected local VeriDark layout:
  data/veridark/
    train/<one JSON file per pair>
    val/<one JSON file per pair>
    test/<one JSON file per pair>
Each JSON file must contain {"id": str, "pair": [text1, text2], "same": bool}.
"""


def load_split(data_dir: Path, split: str) -> list[dict]:
    """Load only top-level pair JSON files in the named split directory."""
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    split_dir = Path(data_dir) / split
    if not split_dir.is_dir():
        return []

    pairs = []
    for file_path in sorted(split_dir.glob("*.json")):
        with file_path.open(encoding="utf-8") as file_handle:
            item = json.load(file_handle)
        pair_texts = item.get("pair")
        if (
            not isinstance(item.get("id"), str)
            or not isinstance(pair_texts, list)
            or len(pair_texts) != 2
            or not all(isinstance(text, str) for text in pair_texts)
            or not isinstance(item.get("same"), bool)
        ):
            raise ValueError(f"Invalid pair record: {file_path}")
        pairs.append(item)
    return pairs


def _persona(persona_id: str, text: str) -> Persona:
    return Persona(
        persona_id=persona_id,
        marketplace="veridark-research-dataset",
        handle=persona_id,
        identifiers=[],
        texts=[TextSample(text=text, posted_at=FIXED_TIMESTAMP)],
        first_seen=FIXED_TIMESTAMP,
        last_seen=FIXED_TIMESTAMP,
    )


def score_pairs(pairs: list[dict]) -> list[tuple[bool, float]]:
    """Score text pairs using the existing stylometry pillar without identifiers."""
    scored = []
    for item in pairs:
        text_a, text_b = item["pair"]
        persona_a = _persona(f"{item['id']}-a", text_a)
        persona_b = _persona(f"{item['id']}-b", text_b)
        scored.append((item["same"], compare(persona_a, persona_b).score))
    return scored


def _auc(scored: list[tuple[bool, float]]) -> float | None:
    labels = [int(label) for label, _ in scored]
    scores = [score for _, score in scored]
    if len(set(labels)) < 2:
        return None
    return float(roc_auc_score(labels, scores))


def _threshold_metrics(scored: list[tuple[bool, float]], threshold: float) -> tuple[float, float, float]:
    labels = [int(label) for label, _ in scored]
    predictions = [int(score >= threshold) for _, score in scored]
    return (
        float(precision_score(labels, predictions, zero_division=0)),
        float(recall_score(labels, predictions, zero_division=0)),
        float(f1_score(labels, predictions, zero_division=0)),
    )


def choose_val_threshold(scored: list[tuple[bool, float]]) -> float:
    """Choose the threshold with the best validation F1; ties prefer higher cutoffs."""
    if not scored:
        raise ValueError("Cannot choose a threshold: validation split is empty")
    candidates = sorted({score for _, score in scored} | {0.0, 1.0})
    return max(candidates, key=lambda threshold: (_threshold_metrics(scored, threshold)[2], threshold))


def _split_summary(scored: list[tuple[bool, float]]) -> tuple[int, int, int, float | None, float | None, float | None]:
    same_scores = [score for same, score in scored if same]
    different_scores = [score for same, score in scored if not same]
    return (
        len(scored),
        len(same_scores),
        len(different_scores),
        _auc(scored),
        mean(same_scores) if same_scores else None,
        mean(different_scores) if different_scores else None,
    )


def evaluate(data_dir: Path = DEFAULT_DATA_DIR) -> int:
    data_dir = Path(data_dir)
    if not data_dir.is_dir() or any(not (data_dir / split).is_dir() for split in SPLITS):
        print(EXPECTED_LAYOUT, end="")
        return 0

    raw_splits = {split: load_split(data_dir, split) for split in SPLITS}
    if not raw_splits["val"] or not raw_splits["test"]:
        print("Validation and test splits must both contain at least one pair.")
        print(EXPECTED_LAYOUT, end="")
        return 0

    scored_splits = {split: score_pairs(pairs) for split, pairs in raw_splits.items()}
    print("Stylometry VeriDark pair verification (scores are not calibrated probabilities)")
    print(f"Data directory: {data_dir}")
    print(f"{'split':<8}{'pairs':>9}{'same':>9}{'different':>12}{'AUC':>10}{'mean same':>13}{'mean different':>17}")
    for split in SPLITS:
        count, same_count, different_count, auc, same_mean, different_mean = _split_summary(scored_splits[split])
        auc_text = f"{auc:.3f}" if auc is not None else "n/a"
        same_text = f"{same_mean:.3f}" if same_mean is not None else "n/a"
        different_text = f"{different_mean:.3f}" if different_mean is not None else "n/a"
        print(
            f"{split:<8}{count:>9}{same_count:>9}{different_count:>12}"
            f"{auc_text:>10}{same_text:>13}{different_text:>17}"
        )

    threshold = choose_val_threshold(scored_splits["val"])
    precision, recall, f1 = _threshold_metrics(scored_splits["test"], threshold)
    print(f"Validation-selected threshold (best F1): {threshold:.3f}")
    print(f"Test precision at validation threshold: {precision:.3f}")
    print(f"Test recall at validation threshold: {recall:.3f}")
    print(f"Test F1 at validation threshold: {f1:.3f}")
    print(
        "Note: texts are reused across pairs, so pairs are not independent; "
        "these metrics may overstate generalisation."
    )
    return 0


def main() -> int:
    return evaluate(DEFAULT_DATA_DIR)


if __name__ == "__main__":
    sys.exit(main())
