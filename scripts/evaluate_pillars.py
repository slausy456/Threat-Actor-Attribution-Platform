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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.data_loader import load_ground_truth, load_personas  # noqa: E402
from app.services.fusion.pipeline import score_pair  # noqa: E402
from app.services.identity_graph import matcher as identity  # noqa: E402
from app.services.infrastructure_scan import matcher as infra  # noqa: E402
from app.services.stylometry import matcher as style  # noqa: E402

PERSONAS = load_personas()
_, PAIRS = load_ground_truth()

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
