from app.data_loader import load_ground_truth, load_personas
from app.services.fusion.pipeline import score_pair
from app.services.fusion.scorer import SignalScores, fuse

PERSONAS = load_personas()
_, PAIRS = load_ground_truth()


def test_fuse_confidence_is_in_range():
    for pair in PAIRS:
        result = score_pair(PERSONAS[pair.persona_a], PERSONAS[pair.persona_b])
        assert 0.0 <= result["confidence"] <= 1.0


def test_same_actor_scenarios_reach_threshold():
    by_scenario = {}
    for pair in PAIRS:
        by_scenario.setdefault(pair.scenario, []).append(pair)

    for scenario in ["pgp_reuse", "wallet_reuse", "infra_only", "style_only", "multi_signal"]:
        scores = []
        for pair in by_scenario[scenario]:
            result = score_pair(PERSONAS[pair.persona_a], PERSONAS[pair.persona_b])
            scores.append(result["confidence"])
        assert sum(score >= 0.5 for score in scores) / len(scores) >= 0.8, scenario


def test_trap_scenarios_stay_below_threshold():
    by_scenario = {}
    for pair in PAIRS:
        by_scenario.setdefault(pair.scenario, []).append(pair)

    for scenario in ["shared_hosting", "copycat_style", "similar_handle", "random"]:
        scores = []
        for pair in by_scenario[scenario]:
            result = score_pair(PERSONAS[pair.persona_a], PERSONAS[pair.persona_b])
            scores.append(result["confidence"])
        assert sum(score >= 0.5 for score in scores) / len(scores) <= 0.2, scenario


def test_higher_pillar_score_never_lowers_confidence():
    a = PERSONAS["P001"]
    b = PERSONAS["P003"]
    baseline = fuse(SignalScores(infrastructure=0.1, identity_graph=0.2, stylometry=0.3))

    higher = fuse(SignalScores(infrastructure=0.4, identity_graph=0.2, stylometry=0.3))
    assert higher["confidence"] >= baseline["confidence"]

    higher2 = fuse(SignalScores(infrastructure=0.1, identity_graph=0.5, stylometry=0.3))
    assert higher2["confidence"] >= baseline["confidence"]

    higher3 = fuse(SignalScores(infrastructure=0.1, identity_graph=0.2, stylometry=0.7))
    assert higher3["confidence"] >= baseline["confidence"]
