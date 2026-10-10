"""
Stylometry pillar: do two personas WRITE alike?

CONTRACT (same for all pillars): compare(a, b) -> SignalResult
  - pure function; symmetric; score in [0, 1]; evidence = human-readable reasons
  - input is Persona.texts (list of TextSample)

Suggested approach: embed each text with sentence-transformers, average per
persona, cosine similarity; optionally add simple features (punctuation habits,
average sentence length, typo patterns) since embeddings alone mostly capture
topic, not style.

Should succeed on: style_only (the hard case), plus agrees on the rest
Expected to be fooled by: copycat_style (copied catchphrases)  <- document how you handle it
"""
from app.models.entities import Persona, SignalResult


def compare(a: Persona, b: Persona) -> SignalResult:
    raise NotImplementedError("stylometry.compare — owner: TODO")
