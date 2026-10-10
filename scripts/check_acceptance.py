"""
Acceptance checks: did the build steps actually meet the project's objectives?

Run from the repo root, then paste the full output to whoever is reviewing:

    python scripts/check_acceptance.py            # everything that applies so far
    python scripts/check_acceptance.py --step 3   # pillars only (3), fusion (4), explain (5)
    python scripts/check_acceptance.py --update-hashes   # ONLY after you reviewed a deliberate change

What it does
  1. TRIPWIRE: the answer key, data model and the existing tests must not change
     silently (an easy way to "pass" is to edit the test or the data).
  2. STATIC RULES: pillar/fusion code must not read ground-truth labels or scenario
     names (that would be cheating), and nothing may touch Tor / live scanning.
  3. BEHAVIOUR: each pillar must win the scenarios it should win and stay low on its
     trap. Fusion must beat every single pillar and also catch the *_restyled actors
     (same actor, deliberately changed writing style) that stylometry alone cannot.
     Explanations must be grounded.

The numeric thresholds below are starting values chosen from docs/pillar_contract.md.
They can be changed, but change them deliberately and say why in the report;
a threshold edited to make a failing result pass proves nothing.

Later steps (API, dashboard, real data) are verified by running them, not by this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

HASH_FILE = ROOT / "scripts" / "protected_hashes.json"
PROTECTED = [
    "backend/app/models/entities.py",
    "scripts/generate_synthetic_data.py",
    "data/synthetic/personas.json",
    "data/synthetic/ground_truth.json",
    "tests/test_synthetic_data.py",
    "tests/test_pillar_contract.py",
    "scripts/check_acceptance.py",
]

# ---- thresholds ------------------------------------------------------------
HIGH = 0.70          # mean score a pillar must reach on scenarios it should win
LOW = 0.30           # mean score ceiling on scenarios it must not match
LOW_MAX = 0.50       # no single negative pair may reach this (per pillar)
STYLE_HIGH = 0.60    # stylometry is noisier; slightly lower bar
STYLE_LOW = 0.45
STYLE_AUC = 0.85
THRESHOLD = 0.50     # decision threshold for F1 / recall / false positives
FUSED_RECALL = 0.80  # each same-actor scenario: share of pairs fused >= THRESHOLD
FUSED_FPR = 0.20     # each different-actor scenario: share of pairs fused >= THRESHOLD

SAME = ["pgp_reuse", "wallet_reuse", "infra_only", "style_only", "multi_signal",
        "pgp_restyled", "wallet_restyled", "infra_restyled"]
RESTYLED = ["pgp_restyled", "wallet_restyled", "infra_restyled"]  # same actor, changed writing style
DIFF = ["shared_hosting", "copycat_style", "similar_handle", "random"]
ALL_SCEN = SAME + DIFF

EXPECT = {  # pillar -> (must be HIGH on, must stay LOW on)
    "identity_graph": (["pgp_reuse", "wallet_reuse", "multi_signal", "pgp_restyled", "wallet_restyled"],
                       ["infra_only", "style_only", "infra_restyled"] + DIFF),
    "infrastructure_scan": (["infra_only", "multi_signal", "infra_restyled"],
                            ["pgp_reuse", "wallet_reuse", "style_only", "pgp_restyled",
                             "wallet_restyled"] + DIFF),
    # stylometry is only expected to win where the actor KEPT their style; on the
    # *_restyled scenarios it is expected to be blind (reported as INFO, not required)
    "stylometry": (["style_only", "multi_signal", "pgp_reuse", "wallet_reuse", "infra_only"],
                   ["copycat_style", "random"]),
}

results: list[tuple[str, str, str]] = []  # (status, name, detail)


def rec(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f"  - {detail}" if detail else ""))


def sha(path: Path) -> str:
    # normalise line endings so Windows (CRLF) and Linux/Mac (LF) checkouts hash the same
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---- 1. tripwire -----------------------------------------------------------
def check_hashes() -> None:
    if not HASH_FILE.exists():
        rec("FAIL", "protected files", "scripts/protected_hashes.json missing")
        return
    known = json.loads(HASH_FILE.read_text())
    for rel in PROTECTED:
        p = ROOT / rel
        if not p.exists():
            rec("FAIL", f"protected: {rel}", "file missing")
        elif known.get(rel) != sha(p):
            rec("FAIL", f"protected: {rel}", "MODIFIED since baseline - review the diff; "
                "if deliberate and justified, run --update-hashes")
        else:
            rec("PASS", f"protected: {rel}", "unchanged")


def update_hashes() -> None:
    HASH_FILE.write_text(json.dumps({r: sha(ROOT / r) for r in PROTECTED}, indent=2) + "\n")
    print(f"baseline written to {HASH_FILE.relative_to(ROOT)}")


# ---- 2. static rules -------------------------------------------------------
CHEAT = [r"ground_truth", r"load_ground_truth", r"PairLabel", r"same_actor",
         r"\bscenario\b", r"['\"]P\d{3}['\"]", r"['\"]A\d{3}['\"]"]
TOR = [r"\.onion", r"\bstem\b", r"torpy", r"socks5", r"onionscan", r"torrc", r":9050", r":9150"]
NET = [r"^\s*(import|from)\s+(requests|urllib|socket|httpx|aiohttp|subprocess|selenium)\b"]


def executable_code(text: str) -> str:
    """Source with comments and docstrings removed, so only real code is inspected."""
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body[0] = ast.Pass()
    return ast.unparse(tree)


def check_static() -> None:
    svc = ROOT / "backend" / "app" / "services"
    files = [p for p in svc.rglob("*.py") if p.name != "__init__.py" or p.stat().st_size > 0]
    cheat_hits, tor_hits, net_hits = [], [], []
    for p in files:
        text = p.read_text(errors="ignore")
        rel = p.relative_to(ROOT).as_posix()
        code = executable_code(text)
        for pat in CHEAT:
            if re.search(pat, code):
                cheat_hits.append(f"{rel} ~ {pat}")
        for pat in TOR:
            if re.search(pat, code, re.I):
                tor_hits.append(f"{rel} ~ {pat}")
        if "llm_explain" not in rel:  # the explanation layer may call an LLM API
            for pat in NET:
                if re.search(pat, code, re.M):
                    net_hits.append(f"{rel} ~ {pat.split('(')[1].split(')')[0]}")
    # docstrings may legitimately mention words; only flag if the NAME appears in executable-looking code
    rec("FAIL" if cheat_hits else "PASS", "services do not read answer key / scenario names",
        "; ".join(cheat_hits[:4]))
    rec("FAIL" if tor_hits else "PASS", "no Tor / live-scan code", "; ".join(tor_hits[:4]))
    rec("FAIL" if net_hits else "PASS", "no network/process imports in pillars or fusion",
        "; ".join(net_hits[:4]))


# ---- scoring helpers -------------------------------------------------------
def auc(pos: list[float], neg: list[float]) -> float:
    if not pos or not neg:
        return float("nan")
    s = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return s / (len(pos) * len(neg))


def f1_at(pairs_scores: list[tuple[bool, float]], thr: float = THRESHOLD) -> float:
    tp = sum(1 for y, s in pairs_scores if y and s >= thr)
    fp = sum(1 for y, s in pairs_scores if not y and s >= thr)
    fn = sum(1 for y, s in pairs_scores if y and s < thr)
    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def load():
    from app.data_loader import load_ground_truth, load_personas
    return load_personas(), load_ground_truth()[1]


def pillar_funcs():
    from app.services.identity_graph import matcher as i
    from app.services.infrastructure_scan import matcher as f
    from app.services.stylometry import matcher as s
    return {"identity_graph": i.compare, "infrastructure_scan": f.compare, "stylometry": s.compare}


# ---- 3. pillars ------------------------------------------------------------
def check_pillars(personas, pairs) -> dict[str, list[float]] | None:
    table: dict[str, dict[str, list[float]]] = {}
    per_pair: dict[str, list[float]] = {}
    for name, fn in pillar_funcs().items():
        try:
            scores = [fn(personas[p.persona_a], personas[p.persona_b]).score for p in pairs]
        except NotImplementedError:
            rec("SKIP", f"pillar {name}", "not implemented yet")
            continue
        except Exception as e:  # noqa: BLE001
            rec("FAIL", f"pillar {name}", f"raised {type(e).__name__}: {e}")
            continue
        per_pair[name] = scores
        by = defaultdict(list)
        for p, s in zip(pairs, scores):
            by[p.scenario].append(s)
        table[name] = by
        high, low = EXPECT[name]
        hi_thr, lo_thr = (STYLE_HIGH, STYLE_LOW) if name == "stylometry" else (HIGH, LOW)
        bad_hi = [f"{s}={mean(by[s]):.2f}" for s in high if mean(by[s]) < hi_thr]
        rec("FAIL" if bad_hi else "PASS", f"{name}: wins its scenarios (mean >= {hi_thr})",
            ", ".join(bad_hi))
        bad_lo = [f"{s}={mean(by[s]):.2f}" for s in low if mean(by[s]) > lo_thr]
        rec("FAIL" if bad_lo else "PASS", f"{name}: stays low on its traps (mean <= {lo_thr})",
            ", ".join(bad_lo))
        if name != "stylometry":
            worst = max((max(by[s]) for s in low), default=0)
            rec("FAIL" if worst >= LOW_MAX else "PASS",
                f"{name}: no single negative pair >= {LOW_MAX}", f"worst={worst:.2f}")
        else:
            a = auc([s for p, s in zip(pairs, scores) if p.same_actor and p.scenario not in RESTYLED],
                    [s for p, s in zip(pairs, scores) if not p.same_actor])
            rec("FAIL" if a < STYLE_AUC else "PASS",
                f"stylometry: AUC >= {STYLE_AUC} (actors who kept their style vs different actors)",
                f"AUC={a:.2f}")
            gap = mean(by["style_only"]) - mean(by["copycat_style"])
            rec("FAIL" if gap < 0.15 else "PASS",
                "stylometry: copycat clearly below real same-author", f"gap={gap:.2f}")
        blind = [s for s in SAME if mean(by[s]) <= lo_thr]
        rec("INFO", f"{name}: blind spots (justify fusion)", ", ".join(blind) or "none")
    if table:
        print("\nmean score per scenario")
        print(f"{'scenario':<16}" + "".join(f"{n[:10]:>12}" for n in table))
        for s in ALL_SCEN:
            print(f"{s:<16}" + "".join(f"{mean(table[n][s]):>12.2f}" if s in table[n] else f"{'-':>12}"
                                       for n in table))
        print()
    return per_pair if len(per_pair) == 3 else None


# ---- 4. fusion -------------------------------------------------------------
def check_fusion(personas, pairs, per_pair) -> list[dict] | None:
    from app.services.fusion.pipeline import score_pair
    if per_pair is None:
        rec("SKIP", "fusion", "needs all three pillars implemented first")
        return None
    fused = []
    for p in pairs:
        r = score_pair(personas[p.persona_a], personas[p.persona_b])
        fused.append(r)
    scores = [r["confidence"] for r in fused]
    by = defaultdict(list)
    for p, s in zip(pairs, scores):
        by[p.scenario].append(s)
    labels = [p.same_actor for p in pairs]
    f_fused = f1_at(list(zip(labels, scores)))
    f_best = {n: f1_at(list(zip(labels, v))) for n, v in per_pair.items()}
    best_name = max(f_best, key=f_best.get)
    rec("INFO", "F1 at threshold 0.5", f"fused={f_fused:.2f}; " +
        ", ".join(f"{n}={v:.2f}" for n, v in f_best.items()))
    rec("PASS" if f_fused > f_best[best_name] else "FAIL",
        "fusion beats the best single pillar (F1)", f"fused={f_fused:.2f} vs {best_name}={f_best[best_name]:.2f}")
    bad = [f"{s}={sum(x >= THRESHOLD for x in by[s]) / len(by[s]):.0%}" for s in SAME
           if sum(x >= THRESHOLD for x in by[s]) / len(by[s]) < FUSED_RECALL]
    rec("FAIL" if bad else "PASS", f"fused catches every same-actor scenario (>= {FUSED_RECALL:.0%})",
        ", ".join(bad))
    bad = [f"{s}={sum(x >= THRESHOLD for x in by[s]) / len(by[s]):.0%}" for s in DIFF
           if sum(x >= THRESHOLD for x in by[s]) / len(by[s]) > FUSED_FPR]
    rec("FAIL" if bad else "PASS", f"fused not fooled by traps (false positives <= {FUSED_FPR:.0%})",
        ", ".join(bad))
    rec("INFO", "overfitting caveat",
        "if weights/thresholds were tuned on these same pairs, also report a held-out result "
        "(e.g. tune on half the actors, test on the other half)")
    return fused


# ---- 5. explanations -------------------------------------------------------
def get_explain():
    for mod in ("app.services.llm_explain", "app.services.llm_explain.explainer"):
        try:
            m = __import__(mod, fromlist=["explain"])
            if hasattr(m, "explain"):
                return m.explain
        except ImportError:
            continue
    return None


def check_explain(personas, pairs, fused) -> None:
    explain = get_explain()
    if explain is None:
        rec("SKIP", "explanation layer", "explain() not found in app.services.llm_explain")
        return
    if fused is None:
        rec("SKIP", "explanation layer", "needs fusion results")
        return
    saved = {k: os.environ.pop(k, None) for k in ("LLM_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
                                                   "GEMINI_API_KEY")}
    try:
        picked, seen = [], set()
        for p, r in zip(pairs, fused):
            if p.scenario not in seen:
                seen.add(p.scenario)
                picked.append((p.scenario, r))
        problems = []
        for scen, r in picked:
            out: list = []
            t = threading.Thread(target=lambda r=r: out.append(explain(r)), daemon=True)
            t.start()
            t.join(20)
            if not out:
                problems.append(f"{scen}: no result in 20s (does it need an API key?)")
                continue
            text = out[0]
            if not isinstance(text, str) or not (20 <= len(text) <= 1200):
                problems.append(f"{scen}: bad length/type")
                continue
            evidence = json.dumps(r.get("evidence", {})) + json.dumps(r.get("breakdown", {}))
            for tok in re.findall(r"PGP-SYN-[A-F0-9]+|bc1qsyn[0-9a-f]+|[0-9a-f]{40,}", text):
                if tok not in evidence:
                    problems.append(f"{scen}: invented identifier {tok[:16]}...")
            if not re.search(r"confiden|likely|possible|suggest|evidence|uncertain|limited", text, re.I):
                problems.append(f"{scen}: no uncertainty language")
        rec("FAIL" if problems else "PASS",
            "explain() works with no API key, is grounded in the evidence, hedges", "; ".join(problems[:3]))
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ---- main ------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["3", "4", "5", "all"], default="all")
    ap.add_argument("--update-hashes", action="store_true")
    a = ap.parse_args()
    if a.update_hashes:
        update_hashes()
        return 0

    print("== tripwire ==")
    check_hashes()
    print("\n== static rules ==")
    check_static()
    print("\n== pillars (step 3) ==")
    personas, pairs = load()
    per_pair = check_pillars(personas, pairs)
    fused = None
    if a.step in ("4", "5", "all"):
        print("== fusion (step 4) ==")
        fused = check_fusion(personas, pairs, per_pair)
    if a.step in ("5", "all"):
        print("\n== explanations (step 5) ==")
        check_explain(personas, pairs, fused)

    n = {s: sum(1 for r in results if r[0] == s) for s in ("PASS", "FAIL", "SKIP", "INFO")}
    print(f"\nSUMMARY: {n['PASS']} passed, {n['FAIL']} failed, {n['SKIP']} skipped")
    if n["FAIL"]:
        print("FAILED:", "; ".join(r[1] for r in results if r[0] == "FAIL"))
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
