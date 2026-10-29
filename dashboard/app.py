"""Local analyst dashboard. It consumes persona records and scores only."""


import sys
from pathlib import Path

# Adds the root repository directory and the backend folder to Python's path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "backend"))


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
.stApp { background: var(--background-color); }
[data-testid="stSidebar"] { background: var(--secondary-background-color); }
.slim-banner { border-left: 4px solid var(--primary-color); padding: .5rem .8rem;
background: var(--secondary-background-color); border-radius: 5px; margin: .3rem 0 1rem; }
.tier-pill { border-radius: 999px; padding: .18rem .58rem; font-size: .82rem;
font-weight: 700; color: #fff; display: inline-block; }
.metric-card { background: var(--secondary-background-color); border: 1px solid #303746;
border-radius: 10px; padding: .85rem 1rem; min-height: 92px; }
.explanation-box { background: var(--secondary-background-color); border-left: 3px solid var(--primary-color);
border-radius: 6px; padding: .8rem 1rem; }
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


st.title("Attribution Review")
st.caption("Evidence-led triage · Local dataset")
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
