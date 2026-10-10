"""
Contract tests: every pillar must obey the same rules.
Pillars still raising NotImplementedError are SKIPPED, not failed — so this file
goes from all-skipped to all-passing as each teammate finishes their pillar.
"""
import pytest

from app.data_loader import load_ground_truth, load_personas
from app.models.entities import SignalResult
from app.services.identity_graph import matcher as identity
from app.services.infrastructure_scan import matcher as infra
from app.services.stylometry import matcher as style

PERSONAS = load_personas()
_, PAIRS = load_ground_truth()
PILLARS = {"identity_graph": identity, "infrastructure_scan": infra, "stylometry": style}


def run(pillar, a, b):
    try:
        return pillar.compare(a, b)
    except NotImplementedError:
        pytest.skip("pillar not implemented yet")


@pytest.mark.parametrize("name", PILLARS)
def test_returns_valid_signal_result_for_every_pair(name):
    for p in PAIRS:
        r = run(PILLARS[name], PERSONAS[p.persona_a], PERSONAS[p.persona_b])
        assert isinstance(r, SignalResult)
        assert 0.0 <= r.score <= 1.0
        assert all(isinstance(e, str) for e in r.evidence)


@pytest.mark.parametrize("name", PILLARS)
def test_is_symmetric(name):
    for p in PAIRS:
        a, b = PERSONAS[p.persona_a], PERSONAS[p.persona_b]
        r1, r2 = run(PILLARS[name], a, b), run(PILLARS[name], b, a)
        assert r1.score == pytest.approx(r2.score, abs=1e-6)


@pytest.mark.parametrize("name", PILLARS)
def test_does_not_mutate_inputs(name):
    p = PAIRS[0]
    a, b = PERSONAS[p.persona_a], PERSONAS[p.persona_b]
    before = (a.model_dump(), b.model_dump())
    run(PILLARS[name], a, b)
    assert (a.model_dump(), b.model_dump()) == before
