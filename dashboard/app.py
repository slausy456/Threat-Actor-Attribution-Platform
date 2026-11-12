"""Local analyst dashboard. It consumes persona records and scores only."""

from __future__ import annotations

from datetime import date
from html import escape
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.client import (
    ApiError, TIER_COLORS, api_base_url, build_candidate_graph, connection_status,
    explain_pair, filter_pairs, filter_personas_by_timeline,
    list_personas, pairs_export_payload, persona_metrics, score_all_pairs,
    search_personas, source_color, timeline_activity, timeline_filter_bounds,
    tier_badge_style,
)

st.set_page_config(page_title="Attribution Review", page_icon="◈", layout="wide")
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: radial-gradient(ellipse at 18% -8%, rgba(91, 54, 164, .20), transparent 38%), #0b0f19; color: #e6eaf2; }
[data-testid="stMain"] > .main { background-image: radial-gradient(rgba(148,163,184,.105) .7px, transparent .7px); background-size: 25px 25px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #111827, #0d1320); border-right: 1px solid rgba(148,163,184,.14); }
[data-testid="stSidebar"] [data-testid="stMetric"] { background: rgba(20,28,43,.8); border: 1px solid rgba(148,163,184,.15); border-radius: 14px; padding: .8rem; }
.block-container { padding-top: 2.1rem; padding-bottom: 3rem; max-width: 1440px; }
h1, h2, h3 { letter-spacing: -.035em; }
h1 { font-size: 2.25rem !important; font-weight: 750 !important; }
[data-testid="stTabs"] [role="tablist"] { gap: .35rem; border-bottom: 1px solid rgba(148,163,184,.16); }
[data-testid="stTabs"] button[role="tab"] { border-radius: 10px 10px 0 0; padding: .7rem 1rem; color: #aab4c5; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: #c4b5fd; border-bottom-color: #8b5cf6; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: rgba(148,163,184,.16) !important; border-radius: 16px !important; }
[data-testid="stDataFrame"] { border: 1px solid rgba(148,163,184,.15); border-radius: 12px; overflow: hidden; }
div.stButton > button, div[data-testid="stDownloadButton"] > button { border-radius: 10px; border: 1px solid rgba(139,92,246,.42); transition: all .18s ease; }
div.stButton > button:hover, div[data-testid="stDownloadButton"] > button:hover { border-color: #22d3ee; color: #e0faff; box-shadow: 0 0 18px rgba(34,211,238,.12); }
.hero { position: relative; overflow: hidden; padding: 1.4rem 1.55rem; margin: .2rem 0 1rem; border: 1px solid rgba(148,163,184,.17); border-radius: 18px; background: linear-gradient(115deg, rgba(22,29,46,.96), rgba(19,22,39,.85)); box-shadow: 0 14px 40px rgba(0,0,0,.2); }
.hero:after { content: ""; position: absolute; inset: 0 0 0 auto; width: 42%; opacity: .35; pointer-events: none; background-image: radial-gradient(circle, #a78bfa 1px, transparent 1.6px), radial-gradient(circle, #22d3ee .8px, transparent 1.5px); background-size: 24px 24px, 37px 37px; background-position: 0 0, 11px 9px; mask-image: linear-gradient(90deg, transparent, #000); }
.hero-kicker { color: #67e8f9; text-transform: uppercase; letter-spacing: .16em; font-size: .72rem; font-weight: 700; }
.hero-title { margin: .35rem 0 .3rem; color: #f8fafc; font-size: 1.75rem; font-weight: 750; letter-spacing: -.04em; }
.hero-copy { color: #aab4c5; font-size: .94rem; }
.slim-banner { border: 1px solid rgba(139,92,246,.28); border-left: 3px solid #8b5cf6; padding: .75rem 1rem;
background: linear-gradient(100deg, rgba(124,58,237,.12), rgba(17,24,39,.7)); border-radius: 10px; margin: .3rem 0 1.2rem; color: #d8deea; }
.tier-pill { border-radius: 999px; padding: .22rem .65rem; font-size: .72rem; letter-spacing: .05em;
font-weight: 750; color: #fff; display: inline-block; border: 1px solid rgba(255,255,255,.16); }
.metric-card { position: relative; overflow: hidden; background: linear-gradient(145deg, rgba(24,32,49,.95), rgba(15,22,35,.95)); border: 1px solid rgba(148,163,184,.16);
border-radius: 14px; padding: 1rem 1.1rem; min-height: 108px; box-shadow: 0 10px 26px rgba(0,0,0,.16); }
.metric-card small { color: #9aa7ba; font-size: .76rem; letter-spacing: .07em; text-transform: uppercase; }
.metric-card h3 { margin: .45rem 0 0; font-size: 1.55rem; color: #f5f7fb; }
.explanation-box { background: rgba(18,26,41,.9); border: 1px solid rgba(34,211,238,.2); border-left: 3px solid #22d3ee;
border-radius: 10px; padding: .9rem 1rem; color: #dbe5f2; }
.section-note { color: #94a3b8; font-size: .86rem; }
</style>""", unsafe_allow_html=True)


def tier_pill(tier: str) -> str:
    return f'<span class="tier-pill" style="background:{TIER_COLORS.get(tier, TIER_COLORS["weak"])}">{tier.upper()}</span>'


@st.cache_data(show_spinner="Scoring persona pairs…")
def cached_score_all_pairs(personas: list[dict]) -> list[dict]:
    total = len(personas) * (len(personas) - 1) // 2
    progress = st.progress(0.0, text=f"scored 0 of {total} pairs")
    partial_table = st.empty()

    def update(scored: list[dict], pair_total: int) -> None:
        count = len(scored)
        progress.progress(count / max(pair_total, 1), text=f"scored {count} of {pair_total} pairs")
        with partial_table.container():
            st.markdown("**Top pairs so far**")
            display_pairs(scored, 15)

    return score_all_pairs(personas, batch_size=200, on_batch=update)


def display_pairs(rows: list[dict], limit: int | None = None) -> None:
    data = [{
        "Persona A": f"{r['persona_a']['persona_id']} · @{r['persona_a']['handle']}",
        "Persona B": f"{r['persona_b']['persona_id']} · @{r['persona_b']['handle']}",
        "Sources": f"{r['persona_a']['marketplace']} ↔ {r['persona_b']['marketplace']}",
        "Tier": r["tier"].upper(), "Confidence": r["confidence"],
    } for r in (rows[:limit] if limit else rows)]
    frame = pd.DataFrame(data)
    if not frame.empty:
        frame = frame.style.map(tier_badge_style, subset=["Tier"])
    st.dataframe(frame, hide_index=True, use_container_width=True, column_config={
        "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.3f")
    })


st.markdown('<div class="hero"><div class="hero-kicker">Threat intelligence · Attribution workspace</div><div class="hero-title">Attribution Review</div><div class="hero-copy">Evidence-led triage across identity, infrastructure, and writing signals.</div></div>', unsafe_allow_html=True)
st.markdown('<div class="slim-banner"><b>Scores are review leads, not proof of attribution.</b> Strong and Moderate require corroboration; single-signal results are Leads.</div>', unsafe_allow_html=True)
with st.expander("How to interpret this dashboard"):
    st.write("Confidence scores use identity, infrastructure, and writing-style signals. Tier rules were evaluated on synthetic data and are not calibrated probabilities. Review underlying evidence before drawing conclusions.")

try:
    api_url = api_base_url()
    all_personas = list_personas(api_url=api_url)
    first_dates = [date.fromisoformat(p["first_seen"][:10]) for p in all_personas]
    last_dates = [date.fromisoformat(p["last_seen"][:10]) for p in all_personas]
    with st.sidebar:
        st.subheader("Workspace")
        st.caption(connection_status())
        if api_url:
            st.caption(f"API · {api_url}")
        date_window = st.date_input("Date range", value=(min(first_dates), max(last_dates)), min_value=min(first_dates), max_value=max(last_dates))
    since, until = timeline_filter_bounds(date_window)
    personas = filter_personas_by_timeline(all_personas, since, until)
    pairs = cached_score_all_pairs(personas)
except (ApiError, ValueError, KeyError) as error:
    st.error(f"Could not load the local dataset or API: {error}")
    st.stop()

persona_by_id = {p["persona_id"]: p for p in personas}
ids = list(persona_by_id)
try:
    configured_call_budget = max(0, int(os.getenv("LLM_SESSION_CALL_BUDGET", "30")))
except ValueError:
    configured_call_budget = 30
st.session_state.setdefault("llm_calls_remaining", configured_call_budget)
st.session_state.setdefault("explained_pairs", {})
with st.sidebar:
    st.metric("LLM calls remaining", st.session_state["llm_calls_remaining"])
tabs = st.tabs(["Overview", "Search", "Compare", "Timeline", "Graph", "Export"])

with tabs[0]:
    metrics = persona_metrics(personas, pairs)
    st.subheader("Workspace overview")
    cards = [("Personas", metrics["personas"]), ("Sources", metrics["sources"]),
             ("Identifiers", metrics["identifiers"]), ("Date span", metrics["date_span"]),
             ("Strong links", metrics["strong"]), ("Moderate links", metrics["moderate"]),
             ("Lead links", metrics["lead"])]
    for offset in range(0, len(cards), 4):
        cols = st.columns(min(4, len(cards) - offset))
        for col, (label, value) in zip(cols, cards[offset:offset + 4]):
            with col:
                st.markdown(f'<div class="metric-card"><small>{label}</small><h3>{value}</h3></div>', unsafe_allow_html=True)
    st.subheader("Top scored pairs")
    display_pairs(pairs, 15)
    if st.button("Explain top 5", key="explain_top_five"):
        top_five = pairs[:5]
        explanation_progress = st.progress(0.0, text=f"explained 0 of {len(top_five)} pairs")
        explanations = []
        for index, pair in enumerate(top_five, start=1):
            explanation = explain_pair(
                pair,
                budget_remaining=st.session_state["llm_calls_remaining"],
            )
            st.session_state["llm_calls_remaining"] = max(
                0, st.session_state["llm_calls_remaining"] - explanation["llm_calls_used"]
            )
            explanations.append((pair, explanation))
            explanation_progress.progress(index / max(len(top_five), 1), text=f"explained {index} of {len(top_five)} pairs")
        st.session_state["explained_pairs"].update({
            tuple(sorted((pair["persona_a"]["persona_id"], pair["persona_b"]["persona_id"]))): explanation
            for pair, explanation in explanations
        })
        st.rerun()
    for pair in pairs[:5]:
        key = tuple(sorted((pair["persona_a"]["persona_id"], pair["persona_b"]["persona_id"])))
        explanation = st.session_state["explained_pairs"].get(key)
        if explanation:
            with st.expander(f"{key[0]} ↔ {key[1]} · {explanation['explanation_label']}"):
                st.write(explanation["explanation"])

with tabs[1]:
    st.subheader("Search personas")
    query_col, source_col, tier_col = st.columns([2, 1, 1])
    query = query_col.text_input("Search ID, handle, or identifier", key="persona_search")
    sources = ["All sources", *sorted({p["marketplace"] for p in personas})]
    selected_source = source_col.selectbox("Source", sources)
    selected_tier = tier_col.selectbox("Tier", ["All tiers", "strong", "moderate", "lead", "weak"])
    matches = search_personas(query, personas) if query else list(personas)
    matches = [p for p in matches if selected_source == "All sources" or p["marketplace"] == selected_source]
    if selected_tier != "All tiers":
        linked_ids = {p["persona_a"]["persona_id"] for p in pairs if p["tier"] == selected_tier} | {p["persona_b"]["persona_id"] for p in pairs if p["tier"] == selected_tier}
        matches = [p for p in matches if p["persona_id"] in linked_ids]
    st.caption(f"Showing {len(matches)} of {len(personas)} personas")
    st.dataframe(pd.DataFrame([{
        "Persona": p["persona_id"], "Handle": f"@{p['handle']}", "Source": p["marketplace"],
        "First seen": p["first_seen"][:10], "Last seen": p["last_seen"][:10],
        "Identifiers": len(p.get("identifiers", [])),
    } for p in matches]), hide_index=True, use_container_width=True)
    if matches:
        prior = st.session_state.get("selected_persona_id")
        default_index = next((i for i, p in enumerate(matches) if p["persona_id"] == prior), 0)
        st.session_state["selected_persona_id"] = st.selectbox("Open persona", [p["persona_id"] for p in matches], index=default_index)

with tabs[2]:
    st.subheader("Compare two personas")
    if len(ids) >= 2:
        a_col, b_col = st.columns(2)
        a_id = a_col.selectbox("Persona A", ids, key="compare_a")
        b_id = b_col.selectbox("Persona B", [i for i in ids if i != a_id], key="compare_b")
        try:
            scored = next((r for r in pairs if {r["persona_a"]["persona_id"], r["persona_b"]["persona_id"]} == {a_id, b_id}), None)
            result = scored
            if result is None:
                result = score_all_pairs([persona_by_id[a_id], persona_by_id[b_id]])[0]
            left, right = st.columns(2)
            for col, p in ((left, persona_by_id[a_id]), (right, persona_by_id[b_id])):
                with col:
                    st.markdown(f"### {p['persona_id']} · @{p['handle']}")
                    st.write(f"**Source:** {p['marketplace']}")
                    st.write(f"**Observed:** {p['first_seen'][:10]} – {p['last_seen'][:10]}")
                    st.write(f"**Identifiers:** {len(p.get('identifiers', []))}")
            conf = float(result["confidence"])
            gauge = go.Figure(go.Indicator(mode="gauge+number", value=conf, number={"valueformat": ".3f"}, title={"text": result["tier"].upper()}, gauge={"axis": {"range": [0, 1]}, "bar": {"color": TIER_COLORS.get(result["tier"], TIER_COLORS["weak"])}, "steps": [{"range": [0, 1], "color": "#252b36"}]}))
            gauge.update_layout(height=260, margin={"t": 50, "b": 10, "l": 30, "r": 30})
            st.plotly_chart(gauge, use_container_width=True)
            scores = result.get("breakdown", {})
            for label, key in (("Identity", "identity_graph"), ("Infrastructure", "infrastructure"), ("Writing style", "stylometry")):
                st.write(f"**{label}** · {float(scores.get(key, 0)):.3f}")
                st.progress(float(scores.get(key, 0)))
            st.markdown("#### Evidence")
            for pillar, evidence in result.get("evidence", {}).items():
                st.markdown(f"**{pillar.replace('_', ' ').title()}**")
                lines = [e.get("description", "") if isinstance(e, dict) else str(e) for e in evidence]
                for line in lines[:4]:
                    st.markdown(f"- {line}")
                if not lines:
                    st.caption("No evidence recorded.")
            pair_key = tuple(sorted((a_id, b_id)))
            explanation = st.session_state["explained_pairs"].get(pair_key)
            if explanation is None and st.button("Explain pair", key=f"explain_{a_id}_{b_id}"):
                explanation = explain_pair(result, budget_remaining=st.session_state["llm_calls_remaining"])
                st.session_state["llm_calls_remaining"] = max(
                    0, st.session_state["llm_calls_remaining"] - explanation["llm_calls_used"]
                )
                st.session_state["explained_pairs"][pair_key] = explanation
                st.rerun()
            if explanation:
                st.markdown(f"**{explanation['explanation_label']}**")
                st.markdown(f'<div class="explanation-box">{escape(explanation["explanation"])}</div>', unsafe_allow_html=True)
        except ApiError as error:
            st.error(f"Comparison failed: {error}")

with tabs[3]:
    st.subheader("Persona activity")
    activity = timeline_activity(personas, since, until)
    bars = activity["bars"]
    if bars:
        frame = pd.DataFrame(bars)
        palette = {source: source_color(source) for source in frame["source"].unique()}
        fig = px.timeline(frame, x_start="start", x_end="end", y="persona_id", color="source", color_discrete_map=palette, hover_data=["first_seen", "last_seen"])
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(height=max(320, 24 * len(bars)), xaxis_title="Observed date", yaxis_title="Persona", legend_title="Source")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Posts per week")
        weekly = activity["posts_per_week"]
        st.bar_chart(pd.DataFrame(weekly).set_index("week") if weekly else pd.DataFrame(columns=["Posts"]))
    else:
        st.info("No activity falls in this date range.")

with tabs[4]:
    st.subheader("Candidate graph")
    st.markdown('<div class="section-note">Explore the strongest scored links around a selected persona. Node colors indicate confidence tier; hover for persona details.</div>', unsafe_allow_html=True)
    if ids:
        center_id = st.selectbox("Centre persona", ids, key="graph_center")
        rows = []
        for pair in pairs:
            a_id, b_id = pair["persona_a"]["persona_id"], pair["persona_b"]["persona_id"]
            if center_id not in (a_id, b_id):
                continue
            other_id = b_id if a_id == center_id else a_id
            rows.append({**pair, "persona": persona_by_id[other_id]})
            if len(rows) == 30:
                break
        if rows:
            st.plotly_chart(build_candidate_graph(persona_by_id[center_id], rows), use_container_width=True)
        else:
            st.info("No candidate links are available in the selected date range.")
        st.markdown(" ".join(tier_pill(t) for t in ("strong", "moderate", "lead", "weak")), unsafe_allow_html=True)
        st.caption("Edge colour shows the confidence tier. Edge labels show the strongest pillar.")

with tabs[5]:
    st.subheader("Export scored pairs")
    rows = filter_pairs(pairs, persona_by_id)
    st.caption(f"{len(rows)} scored pairs in the selected date range")
    for col, (label, output, mime) in zip(st.columns(3), (("CSV", "csv", "text/csv"), ("JSON", "json", "application/json"), ("Report (Markdown)", "markdown", "text/markdown"))):
        payload, _ = pairs_export_payload(rows, output)
        extension = "md" if output == "markdown" else output
        col.download_button(label, payload, file_name=f"scored_pairs.{extension}", mime=mime, key=f"pairs_{output}")
