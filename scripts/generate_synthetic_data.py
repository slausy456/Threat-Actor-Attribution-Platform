"""
Generate a fully synthetic dataset of personas + ground truth.

Why synthetic: lets us develop and test all three pillars on day one, with
KNOWN correct answers, without needing real dark web data (which we must not
collect — see docs/ethics_and_data_sources.md).

Everything here is fake: handles, "PGP keys", "wallets", hashes and text are
randomly generated and deliberately benign (generic digital-goods listings).

Run from repo root:
    python scripts/generate_synthetic_data.py

Outputs (in data/synthetic/):
    personas.json      list[Persona]
    ground_truth.json  {"actors": [...], "pairs": [...]}

Each labelled pair has a `scenario` so we can see WHICH situation a pillar
handles well or badly. Scenarios:

  Same actor (should match):
    pgp_reuse        shares a PGP key, different handle/market
    wallet_reuse     shares a wallet only
    infra_only       shares cert/favicon only (no shared identifiers)
    style_only       shares NOTHING except writing style  <- the hard case
    multi_signal     shares PGP + wallet + infra (easy, high confidence)
    pgp_restyled     shares a PGP key, but the actor DELIBERATELY changed writing style
    wallet_restyled  shares a wallet, but the actor changed writing style
    infra_restyled   shares cert/favicon, but the actor changed writing style
                     (the three *_restyled scenarios are where stylometry is blind and
                      the other pillars must carry the match; they are generated last
                      so the earlier personas and pairs are unchanged)

  Different actors (should NOT match):
    shared_hosting   same generic server banner (weak infra signal = trap)
    copycat_style    copied signature phrases but different habits
    similar_handle   handles look alike, nothing else does
    random           unrelated personas
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.models.entities import (  # noqa: E402
    Actor,
    Identifier,
    IdentifierType as T,
    PairLabel,
    Persona,
    TextSample,
)

SEED = 42
rng = random.Random(SEED)
BASE_DATE = datetime(2024, 1, 1)

MARKETS = ["market_alpha", "market_beta", "market_gamma", "forum_delta"]
HANDLE_WORDS = ["shadow", "ghost", "silent", "iron", "neon", "crimson", "echo",
                "frost", "nova", "raven", "cipher", "ember", "onyx", "pixel"]
HANDLE_NOUNS = ["trader", "vendor", "fox", "wolf", "hawk", "smith", "labs",
                "works", "hub", "king", "node", "forge"]
ITEMS = ["e-book bundles", "design templates", "stock photo packs",
         "software license keys", "font collections", "course notes"]

GENERIC_BANNERS = ["nginx/1.18.0 (Ubuntu)", "Apache/2.4.41 (Ubuntu)"]  # very common

# sentence templates — benign marketplace-style listing text
TEMPLATES = [
    "{item} available now, delivery within {n} hours",
    "stock refreshed today for {item}",
    "all {item} are tested before dispatch",
    "bulk orders of {item} get a discount",
    "questions about {item}? message me before ordering",
    "new batch of {item} just arrived",
]
OPENERS = ["welcome to my shop", "thanks for checking my listing", "hello and welcome"]
CLOSERS = ["see you soon", "thanks for reading", "order whenever ready"]
JOINERS = [" and also ", ", while ", " plus "]

TYPO_POOL = {
    "delivery": "delievery", "before": "befor", "available": "availble",
    "questions": "quesitons", "tested": "tesed", "ordering": "ordring",
    "discount": "discont", "arrived": "arived", "today": "todya",
}
SIGNATURE_PHRASES = ["no refunds after 24h", "trusted since day one", "fast and quiet",
                     "cheers mate", "quality first always", "ask before you buy",
                     "stay safe out there", "always fresh stock"]


# ----------------------------------------------------------------- helpers
def _hex(n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def make_handle() -> str:
    h = f"{rng.choice(HANDLE_WORDS)}_{rng.choice(HANDLE_NOUNS)}"
    return h + (str(rng.randint(1, 99)) if rng.random() < 0.4 else "")


def make_pgp() -> str:
    return f"PGP-SYN-{_hex(16).upper()}"


def make_wallet() -> str:
    return f"bc1qsyn{_hex(30)}"  # obviously-fake synthetic prefix


def make_cert() -> str:
    return hashlib.sha256(_hex(12).encode()).hexdigest()


def make_favicon() -> str:
    return str(rng.randint(-2_000_000_000, 2_000_000_000))


class StyleProfile:
    """An actor's writing habits. THIS is what stylometry should pick up."""

    def __init__(self, phrases=None):
        self.lowercase = rng.random() < 0.5
        self.end_punct = rng.choice([".", "!", "...", ""])
        self.long_sentences = rng.random() < 0.5
        self.typos = dict(rng.sample(sorted(TYPO_POOL.items()), 3))
        self.phrases = phrases or rng.sample(SIGNATURE_PHRASES, 2)
        self.opener = rng.choice(OPENERS)
        self.closer = rng.choice(CLOSERS)

    def is_distinct_from(self, other: "StyleProfile") -> bool:
        """True if an actor switching from self to other really changed habits:
        at least one directly observable habit differs, and no shared misspellings,
        catchphrases, opener or closer carry over."""
        observable = (self.lowercase != other.lowercase) or (self.end_punct != other.end_punct)
        return (observable
                and not (set(self.typos) & set(other.typos))
                and not (set(self.phrases) & set(other.phrases))
                and self.opener != other.opener
                and self.closer != other.closer)

    def write(self) -> str:
        def one() -> str:
            return rng.choice(TEMPLATES).format(item=rng.choice(ITEMS), n=rng.choice([12, 24, 48]))

        s = one()
        if self.long_sentences:
            s += rng.choice(JOINERS) + one()
        parts = [self.opener, s, rng.choice(self.phrases), self.closer]
        text = (self.end_punct + " ").join(parts) + self.end_punct
        for right, wrong in self.typos.items():
            text = text.replace(right, wrong)
        return text.lower() if self.lowercase else text.capitalize()


# ----------------------------------------------------------------- builders
_counter = {"persona": 0}


def new_persona(style: StyleProfile, marketplace: str, *, identifiers=None,
                handle: str | None = None, n_texts: int = 6) -> Persona:
    _counter["persona"] += 1
    pid = f"P{_counter['persona']:03d}"
    first = BASE_DATE + timedelta(days=rng.randint(0, 300))
    texts = [
        TextSample(text=style.write(), posted_at=first + timedelta(days=rng.randint(1, 120)))
        for _ in range(n_texts)
    ]
    ids = list(identifiers or [])
    h = handle or make_handle()
    ids.append(Identifier(type=T.HANDLE, value=h))
    return Persona(
        persona_id=pid, marketplace=marketplace, handle=h, identifiers=ids,
        texts=texts, first_seen=first,
        last_seen=max(t.posted_at for t in texts),
    )


def fresh_ids(pgp=True, wallet=True, infra=True) -> list[Identifier]:
    out = []
    if pgp:
        out.append(Identifier(type=T.PGP_KEY, value=make_pgp()))
    if wallet:
        out.append(Identifier(type=T.WALLET, value=make_wallet()))
    if infra:
        out += [Identifier(type=T.CERT_HASH, value=make_cert()),
                Identifier(type=T.FAVICON_HASH, value=make_favicon()),
                Identifier(type=T.SERVER_BANNER, value=f"custom-srv/{rng.randint(1,9)}.{rng.randint(0,9)}")]
    return out


def pick(ids: list[Identifier], *types: T) -> list[Identifier]:
    return [i for i in ids if i.type in types]


def distinct_style_pair() -> tuple["StyleProfile", "StyleProfile"]:
    """Two style profiles for ONE actor who deliberately changes how they write."""
    a = StyleProfile()
    while True:
        b = StyleProfile()
        if a.is_distinct_from(b):
            return a, b


def two_markets() -> tuple[str, str]:
    a, b = rng.sample(MARKETS, 2)
    return a, b


# ----------------------------------------------------------------- main
def build() -> tuple[list[Persona], list[Actor], list[PairLabel]]:
    personas: list[Persona] = []
    actors: list[Actor] = []
    pairs: list[PairLabel] = []
    actor_n = {"n": 0}

    def register(*ps: Persona) -> str:
        actor_n["n"] += 1
        aid = f"A{actor_n['n']:03d}"
        actors.append(Actor(actor_id=aid, persona_ids=[p.persona_id for p in ps]))
        personas.extend(ps)
        return aid

    # ---- SAME-ACTOR scenarios: each actor appears as two personas
    same_actor_plan = (["pgp_reuse"] * 3 + ["wallet_reuse"] * 3 + ["infra_only"] * 3
                       + ["style_only"] * 4 + ["multi_signal"] * 2)

    for scenario in same_actor_plan:
        style = StyleProfile()
        base = fresh_ids()
        m1, m2 = two_markets()

        if scenario == "pgp_reuse":
            shared = pick(base, T.PGP_KEY)
            p1 = new_persona(style, m1, identifiers=shared + fresh_ids(pgp=False, infra=True))
            p2 = new_persona(style, m2, identifiers=shared + fresh_ids(pgp=False, infra=True))
        elif scenario == "wallet_reuse":
            shared = pick(base, T.WALLET)
            p1 = new_persona(style, m1, identifiers=shared + fresh_ids(wallet=False, infra=True))
            p2 = new_persona(style, m2, identifiers=shared + fresh_ids(wallet=False, infra=True))
        elif scenario == "infra_only":
            shared = pick(base, T.CERT_HASH, T.FAVICON_HASH)
            p1 = new_persona(style, m1, identifiers=fresh_ids(infra=False) + shared)
            p2 = new_persona(style, m2, identifiers=fresh_ids(infra=False) + shared)
        elif scenario == "style_only":
            # nothing shared but the writing — the hard case
            p1 = new_persona(style, m1, identifiers=fresh_ids())
            p2 = new_persona(style, m2, identifiers=fresh_ids())
        else:  # multi_signal
            shared = pick(base, T.PGP_KEY, T.WALLET, T.CERT_HASH, T.FAVICON_HASH)
            p1 = new_persona(style, m1, identifiers=shared)
            p2 = new_persona(style, m2, identifiers=shared)

        register(p1, p2)
        pairs.append(PairLabel(persona_a=p1.persona_id, persona_b=p2.persona_id,
                               same_actor=True, scenario=scenario))

    # ---- DIFFERENT-ACTOR traps (hard negatives)
    for _ in range(3):  # shared_hosting: identical generic banner, nothing else
        banner = Identifier(type=T.SERVER_BANNER, value=rng.choice(GENERIC_BANNERS))
        ps = []
        for m in two_markets():
            ids = fresh_ids(infra=False) + [banner]
            ps.append(new_persona(StyleProfile(), m, identifiers=ids))
        register(ps[0]); register(ps[1])
        pairs.append(PairLabel(persona_a=ps[0].persona_id, persona_b=ps[1].persona_id,
                               same_actor=False, scenario="shared_hosting"))

    for _ in range(3):  # copycat_style: same signature phrases, otherwise different
        orig = StyleProfile()
        copy = StyleProfile(phrases=list(orig.phrases))  # copied catchphrases only
        m1, m2 = two_markets()
        pa = new_persona(orig, m1, identifiers=fresh_ids())
        pb = new_persona(copy, m2, identifiers=fresh_ids())
        register(pa); register(pb)
        pairs.append(PairLabel(persona_a=pa.persona_id, persona_b=pb.persona_id,
                               same_actor=False, scenario="copycat_style"))

    for _ in range(3):  # similar_handle: look-alike handles, nothing else in common
        base_handle = make_handle()
        m1, m2 = two_markets()
        pa = new_persona(StyleProfile(), m1, identifiers=fresh_ids(), handle=base_handle)
        pb = new_persona(StyleProfile(), m2, identifiers=fresh_ids(), handle=base_handle.replace("_", "") + "x")
        register(pa); register(pb)
        pairs.append(PairLabel(persona_a=pa.persona_id, persona_b=pb.persona_id,
                               same_actor=False, scenario="similar_handle"))

    # ---- filler single-persona actors (noise) + random negatives
    for _ in range(6):
        register(new_persona(StyleProfile(), rng.choice(MARKETS), identifiers=fresh_ids()))

    actor_of = {pid: a.actor_id for a in actors for pid in a.persona_ids}
    seen = {frozenset((p.persona_a, p.persona_b)) for p in pairs}
    ids = [p.persona_id for p in personas]
    added = 0
    while added < 20:
        a, b = rng.sample(ids, 2)
        if actor_of[a] != actor_of[b] and frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            pairs.append(PairLabel(persona_a=a, persona_b=b, same_actor=False, scenario="random"))
            added += 1

    # ---- RESTYLED same-actor scenarios. Appended LAST on purpose: the generator is
    # sequential, so everything above stays byte-identical to the earlier dataset.
    for scenario in ["pgp_restyled"] * 3 + ["wallet_restyled"] * 3 + ["infra_restyled"] * 3:
        style_a, style_b = distinct_style_pair()
        base = fresh_ids()
        m1, m2 = two_markets()
        if scenario == "pgp_restyled":
            shared = pick(base, T.PGP_KEY)
            p1 = new_persona(style_a, m1, identifiers=shared + fresh_ids(pgp=False, infra=True))
            p2 = new_persona(style_b, m2, identifiers=shared + fresh_ids(pgp=False, infra=True))
        elif scenario == "wallet_restyled":
            shared = pick(base, T.WALLET)
            p1 = new_persona(style_a, m1, identifiers=shared + fresh_ids(wallet=False, infra=True))
            p2 = new_persona(style_b, m2, identifiers=shared + fresh_ids(wallet=False, infra=True))
        else:  # infra_restyled
            shared = pick(base, T.CERT_HASH, T.FAVICON_HASH)
            p1 = new_persona(style_a, m1, identifiers=fresh_ids(infra=False) + shared)
            p2 = new_persona(style_b, m2, identifiers=fresh_ids(infra=False) + shared)
        register(p1, p2)
        pairs.append(PairLabel(persona_a=p1.persona_id, persona_b=p2.persona_id,
                               same_actor=True, scenario=scenario))

    return personas, actors, pairs


def main() -> None:
    personas, actors, pairs = build()
    out = REPO_ROOT / "data" / "synthetic"
    out.mkdir(parents=True, exist_ok=True)

    (out / "personas.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in personas], indent=2))
    (out / "ground_truth.json").write_text(json.dumps(
        {"actors": [a.model_dump() for a in actors],
         "pairs": [p.model_dump() for p in pairs]}, indent=2))

    pos = sum(p.same_actor for p in pairs)
    print(f"personas: {len(personas)} | actors: {len(actors)} | "
          f"pairs: {len(pairs)} ({pos} same-actor, {len(pairs) - pos} different)")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
