from fastapi.testclient import TestClient

from app.main import app
from app.services.fusion.scorer import tier
from app.services.llm_explain import explain


def test_tier_boundaries():
    assert tier(0.90) == "strong"
    assert tier(0.70) == "moderate"
    assert tier(0.699) == "weak"


def test_explanation_includes_tier_sentence():
    text = explain({"confidence": 0.75, "breakdown": {}, "evidence": {}})
    assert "Tier: moderate lead (confidence 0.75); this remains tentative and the evidence is not conclusive." in text


def test_compare_and_candidates_include_tier():
    client = TestClient(app)

    comparison = client.post("/compare", json={"a": "P001", "b": "P002"})
    assert comparison.status_code == 200
    assert comparison.json()["tier"] == "strong"
    assert "Tier: strong lead" in comparison.json()["explanation"]

    candidates = client.get("/personas/P001/candidates", params={"top": 3})
    assert candidates.status_code == 200
    assert all(candidate["tier"] in {"strong", "moderate", "weak"} for candidate in candidates.json())