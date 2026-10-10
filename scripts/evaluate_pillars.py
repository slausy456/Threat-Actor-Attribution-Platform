"""
Print mean score per scenario for each pillar (and fused, once all exist).
This table is your main project result: it shows where each pillar is blind
and where fusion fixes it.

    python scripts/evaluate_pillars.py
"""
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from sklearn.metrics import f1_score, precision_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.data_loader import load_ground_truth, load_personas  # noqa: E402
from app.services.fusion.pipeline import score_pair  # noqa: E402
from app.services.identity_graph import matcher as identity  # noqa: E402
from app.services.infrastructure_scan import matcher as infra  # noqa: E402
from app.services.stylometry import matcher as style  # noqa: E402

PERSONAS = load_personas()
_, PAIRS = load_ground_truth()


def score_thresholds(scores: list[float], threshold: float = 0.5) -> tuple[float, float, float]:
    labels = [p.same_actor for p in PAIRS]
    preds = [1 if score >= threshold else 0 for score in scores]
    return (
        precision_score(labels, preds, zero_division=0),
        recall_score(labels, preds, zero_division=0),
        f1_score(labels, preds, zero_division=0),
    )

COLUMNS = {"identity": identity.compare, "infra": infra.compare, "style": style.compare}
rows = defaultdict(lambda: defaultdict(list))
order = []

for p in PAIRS:
    a, b = PERSONAS[p.persona_a], PERSONAS[p.persona_b]
    key = (p.scenario, p.same_actor)
    if key not in order:
        order.append(key)
    for col, fn in COLUMNS.items():
        try:
            rows[key][col].append(fn(a, b).score)
        except NotImplementedError:
            pass
    try:
        rows[key]["FUSED"].append(score_pair(a, b)["confidence"])
    except NotImplementedError:
        pass

cols = [*COLUMNS, "FUSED"]
print(f"{'scenario':<16}{'same?':<7}" + "".join(f"{c:>10}" for c in cols))
for key in sorted(order, key=lambda k: (not k[1], k[0])):
    scen, same = key
    cells = [f"{mean(rows[key][c]):>10.2f}" if rows[key][c] else f"{'—':>10}" for c in cols]
    print(f"{scen:<16}{('YES' if same else 'no'):<7}" + "".join(cells))

fused_scores = [score_pair(PERSONAS[p.persona_a], PERSONAS[p.persona_b])["confidence"] for p in PAIRS]
precision, recall, f1 = score_thresholds(fused_scores)
print()
print(f"overall fused precision={precision:.3f} recall={recall:.3f} f1={f1:.3f}")

by_scenario: dict[str, list[float]] = defaultdict(list)
for p, s in zip(PAIRS, fused_scores):
    by_scenario[p.scenario].append(s)

for scenario in sorted(by_scenario):
    labels = [p.same_actor for p in PAIRS if p.scenario == scenario]
    preds = [1 if score >= 0.5 else 0 for score in by_scenario[scenario]]
    print(
        f"{scenario}: precision={precision_score(labels, preds, zero_division=0):.3f}, "
        f"recall={recall_score(labels, preds, zero_division=0):.3f}, "
        f"f1={f1_score(labels, preds, zero_division=0):.3f}"
    )
