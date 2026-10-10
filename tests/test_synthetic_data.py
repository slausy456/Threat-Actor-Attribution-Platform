"""
Sanity tests for the synthetic dataset. If these pass, the answer key is
trustworthy — so later pillar tests can rely on it.
"""
from collections import defaultdict

import pytest

from app.data_loader import load_ground_truth, load_personas
from app.models.entities import IdentifierType as T

PERSONAS = load_personas()
ACTORS, PAIRS = load_ground_truth()


def by_scenario():
    d = defaultdict(list)
    for p in PAIRS:
        d[p.scenario].append(p)
    return d


def shared(pair, *types):
    a, b = PERSONAS[pair.persona_a], PERSONAS[pair.persona_b]
    return a.values_of(*types) & b.values_of(*types)


def test_every_pair_references_real_personas():
    for p in PAIRS:
        assert p.persona_a in PERSONAS and p.persona_b in PERSONAS
        assert p.persona_a != p.persona_b


def test_labels_agree_with_actor_table():
    actor_of = {pid: a.actor_id for a in ACTORS for pid in a.persona_ids}
    for p in PAIRS:
        assert (actor_of[p.persona_a] == actor_of[p.persona_b]) == p.same_actor


def test_all_scenarios_present():
    expected = {"pgp_reuse", "wallet_reuse", "infra_only", "style_only", "multi_signal",
                "pgp_restyled", "wallet_restyled", "infra_restyled",
                "shared_hosting", "copycat_style", "similar_handle", "random"}
    assert set(by_scenario()) == expected


def test_every_persona_has_text_and_handle():
    for p in PERSONAS.values():
        assert len(p.texts) >= 3
        assert p.handle in p.values_of(T.HANDLE)


@pytest.mark.parametrize("scenario,types", [
    ("pgp_reuse", (T.PGP_KEY,)),
    ("wallet_reuse", (T.WALLET,)),
    ("infra_only", (T.CERT_HASH, T.FAVICON_HASH)),
    ("pgp_restyled", (T.PGP_KEY,)),
    ("wallet_restyled", (T.WALLET,)),
    ("infra_restyled", (T.CERT_HASH, T.FAVICON_HASH)),
])
def test_single_signal_scenarios_share_that_signal(scenario, types):
    for pair in by_scenario()[scenario]:
        assert shared(pair, *types), f"{scenario} pair shares nothing: {pair}"


def test_style_only_shares_no_identifiers_or_infra():
    """The hard case: if this fails, 'style_only' isn't actually hard."""
    for pair in by_scenario()["style_only"]:
        assert not shared(pair, T.PGP_KEY, T.WALLET, T.CERT_HASH, T.FAVICON_HASH)


def test_pgp_reuse_does_not_leak_other_identity_signals():
    for pair in by_scenario()["pgp_reuse"]:
        assert not shared(pair, T.WALLET)


def test_different_actors_never_share_strong_identifiers():
    for pair in PAIRS:
        if not pair.same_actor:
            assert not shared(pair, T.PGP_KEY, T.WALLET, T.CERT_HASH, T.FAVICON_HASH)


def test_shared_hosting_trap_shares_only_the_generic_banner():
    for pair in by_scenario()["shared_hosting"]:
        assert shared(pair, T.SERVER_BANNER)


def test_generation_is_deterministic(tmp_path):
    """Same seed -> same dataset, so teammates all work on identical data."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "gen", Path(__file__).parent.parent / "scripts" / "generate_synthetic_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    personas, _, pairs = gen.build()
    assert {p.persona_id for p in personas} == set(PERSONAS)
    assert len(pairs) == len(PAIRS)


# ---- restyled scenarios: same actor, deliberately different writing style --------------

RESTYLED = ["pgp_restyled", "wallet_restyled", "infra_restyled"]


def _observable_style(persona):
    """(is fully lowercase?, sentence-ending habit) - what a reader can see directly."""
    texts = [t.text for t in persona.texts]
    lower = all(t == t.lower() for t in texts)
    ends = {t[-3:] if t.endswith("...") else (t[-1] if t[-1] in ".!" else "") for t in texts}
    return lower, frozenset(ends)


def test_restyled_pairs_really_changed_style():
    """If this fails, 'restyled' pairs are not hard for stylometry and prove nothing."""
    for scenario in RESTYLED:
        pairs = by_scenario()[scenario]
        assert len(pairs) == 3
        for pair in pairs:
            a, b = PERSONAS[pair.persona_a], PERSONAS[pair.persona_b]
            assert _observable_style(a) != _observable_style(b), f"{scenario}: same visible style"


def test_restyled_pairs_are_same_actor_with_exactly_their_signal():
    for pair in by_scenario()["pgp_restyled"]:
        assert not shared(pair, T.WALLET, T.CERT_HASH, T.FAVICON_HASH)
    for pair in by_scenario()["wallet_restyled"]:
        assert not shared(pair, T.PGP_KEY, T.CERT_HASH, T.FAVICON_HASH)
    for pair in by_scenario()["infra_restyled"]:
        assert not shared(pair, T.PGP_KEY, T.WALLET)
    for scenario in RESTYLED:
        assert all(p.same_actor for p in by_scenario()[scenario])
