import pytest

from app.data_loader import load_personas
from app.models.entities import Identifier, IdentifierType
from app.services.fusion.scorer import (
    HARD_IDENTIFIER_MIN,
    SINGLE_SIGNAL_CAP,
    SignalScores,
    fuse,
)
from app.services.identity_graph.matcher import compare as compare_identity
from app.services.infrastructure_scan import matcher as infrastructure


def _persona_with(identifier_type, value):
    persona = load_personas()["P001"].model_copy(deep=True)
    persona.identifiers = [Identifier(type=identifier_type, value=value)]
    return persona


def test_single_pillar_match_is_capped_and_marked_as_lead():
    result = fuse(SignalScores(infrastructure=0.0, identity_graph=1.0, stylometry=0.0))

    assert result["single_signal"] is True
    assert result["raw_confidence"] > SINGLE_SIGNAL_CAP
    assert result["confidence"] == SINGLE_SIGNAL_CAP
    assert result["tier"] == "lead"


def test_two_pillar_match_is_not_capped():
    result = fuse(SignalScores(infrastructure=1.0, identity_graph=1.0, stylometry=0.0))

    assert result["single_signal"] is False
    assert result["confidence"] == result["raw_confidence"]
    assert result["tier"] == "strong"


def test_banner_score_falls_as_persona_frequency_rises(monkeypatch):
    banner = "rare-test-banner"
    a = _persona_with(IdentifierType.SERVER_BANNER, banner)
    b = _persona_with(IdentifierType.SERVER_BANNER, banner)
    monkeypatch.setattr(infrastructure, "_banner_persona_frequencies", lambda: {banner: 2})
    rare_score = infrastructure.compare(a, b).score
    monkeypatch.setattr(infrastructure, "_banner_persona_frequencies", lambda: {banner: 20})
    common_score = infrastructure.compare(a, b).score

    assert rare_score > common_score
    assert rare_score == 0.1
    assert common_score == 0.05
    monkeypatch.setattr(
        infrastructure,
        "_banner_persona_frequencies",
        lambda: {"nginx/1.18.0 (Ubuntu)": 4},
    )
    assert infrastructure._banner_score("nginx/1.18.0 (Ubuntu)") == 0.05

    shared_banners = [f"banner-{index}" for index in range(6)]
    a.identifiers = [
        Identifier(type=IdentifierType.SERVER_BANNER, value=value)
        for value in shared_banners
    ]
    b.identifiers = [
        Identifier(type=IdentifierType.SERVER_BANNER, value=value)
        for value in shared_banners
    ]
    monkeypatch.setattr(
        infrastructure,
        "_banner_persona_frequencies",
        lambda: {value: 2 for value in shared_banners},
    )
    assert infrastructure.compare(a, b).score == 0.3


def test_handle_only_identity_match_stays_at_or_below_point_15():
    a = _persona_with(IdentifierType.HANDLE, "same_handle")
    b = _persona_with(IdentifierType.HANDLE, "same_handle")

    result = compare_identity(a, b)

    assert result.score <= 0.15


@pytest.mark.parametrize("kind", ["pgp", "wallet", "cert_hash"])
def test_lone_hard_identifier_skips_single_signal_cap(kind):
    scores = SignalScores(infrastructure=0.0, identity_graph=0.0, stylometry=0.0)
    pillar = "infrastructure" if kind == "cert_hash" else "identity_graph"
    setattr(scores, pillar, HARD_IDENTIFIER_MIN)
    result = fuse(scores, evidence={pillar: [{"kind": kind, "description": "exact shared identifier"}]})

    assert result["single_signal"] is False
    assert result["confidence"] == result["raw_confidence"]


@pytest.mark.parametrize("kind,pillar", [
    ("favicon_hash", "infrastructure"),
    ("banner", "infrastructure"),
    ("handle", "identity_graph"),
    ("style", "stylometry"),
])
def test_lone_soft_identifier_remains_capped(kind, pillar):
    scores = SignalScores(infrastructure=0.0, identity_graph=0.0, stylometry=0.0)
    setattr(scores, pillar, 1.0)
    result = fuse(scores, evidence={pillar: [{"kind": kind, "description": "weak or non-exact signal"}]})

    assert result["single_signal"] is True
    assert result["confidence"] == SINGLE_SIGNAL_CAP
