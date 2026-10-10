"""Load the synthetic dataset (and later, real research datasets) into models."""
from __future__ import annotations

import json
from pathlib import Path

from app.models.entities import Actor, PairLabel, Persona

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def load_personas(directory: Path = DEFAULT_DIR) -> dict[str, Persona]:
    """Return {persona_id: Persona}."""
    raw = json.loads((directory / "personas.json").read_text())
    return {p["persona_id"]: Persona(**p) for p in raw}


def load_ground_truth(directory: Path = DEFAULT_DIR) -> tuple[list[Actor], list[PairLabel]]:
    raw = json.loads((directory / "ground_truth.json").read_text())
    return ([Actor(**a) for a in raw["actors"]], [PairLabel(**p) for p in raw["pairs"]])
