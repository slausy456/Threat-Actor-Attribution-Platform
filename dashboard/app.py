"""Local analyst dashboard for persona search, comparison, and review."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from dashboard.client import (
    ApiError,
    api_base_url,
    build_candidate_graph,
    candidate_export_payload,
    compare_personas,
    filter_personas_by_timeline,
    format_confidence,
    get_candidates,
    get_persona,
    linked_personas,
    list_personas,
    search_personas,
    tier_badge_style,
    timeline_filter_bounds,
)

st.set_page_config(page_title="Attribution Review", page_icon="A", layout="wide")
st.markdown(
    """
    <style>
    .stApp {
        background: var(--background-color);
        color: var(--text-color);
        font-size: 1.05rem;
    }
    [data-testid="stSidebar"] {
        background: var(--secondary-background-color);
        border-right: 1px solid var(--text-color);
    }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: var(--text-color) !important;
        font-size: 1.02rem;
    }
    [data-baseweb="tab"] {
        color: var(--text-color) !important;
        font-size: 1.02rem !important;
    }
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        color: var(--text-color);
        font-size: 1.02rem;
    }
    .scope-banner {
        color: var(--text-color);
        background: var(--secondary-background-color);
        border: 1px solid var(--primary-color);
        border-left: 5px solid var(--primary-color);
        border-radius: 4px;
        padding: 0.85rem 1rem;
        font-size: 1.02rem;
        line-height: 1.5;
    }
    .how-to-read {
        color: var(--text-color);
        font-size: 1rem;
        margin: 0.55rem 0 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Attribution Review")
st.caption("Local dataset analysis | Evidence-led triage")
st.markdown(
    '<div class="scope-banner"><strong>Scores are leads for human review, not proof.</strong> '
    "Tiers come from the synthetic evaluation and are not calibrated probabilities.</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='how-to-read'><strong>How to read this:</strong> tiers are leads; "
    "strong >= 0.90, moderate >= 0.70, weak below 0.70.</div>",
    unsafe_allow_html=True,
)

try:
    api_url = api_base_url()
    with st.sidebar:
        st.subheader("Workspace")
        st.caption(f"API · {api_url}")
        all_personas = list_personas(api_url=api_url)
        first_dates = [date.fromisoformat(item["first_seen"][:10]) for item in all_personas]
        last_dates = [date.fromisoformat(item["last_seen"][:10]) for item in all_personas]
        date_window = st.date_input(
            "Observed date range",
            value=(min(first_dates), max(last_dates)),
            min_value=min(first_dates),
            max_value=max(last_dates),
        )

    since, until = timeline_filter_bounds(date_window)
    personas = filter_personas_by_timeline(all_personas, since, until)
except (ApiError, ValueError, KeyError) as error:
    st.error(f"Could not load the local API: {error}")
    st.stop()

persona_by_id = {persona["persona_id"]: persona for persona in personas}
tabs = st.tabs(["Search", "Candidate Matches", "Actor Profile", "Graph View", "Export"])

with tabs[0]:
    query = st.text_input("Persona ID, handle, or identifier", key="persona_search")
    matches = search_personas(query, personas)
    if query:
        st.caption(f"{len(matches)} matching personas")
        if matches:
            match_ids = [item["persona_id"] for item in matches]
            selected_match = st.selectbox(
                "Matching personas",
                match_ids,
                format_func=lambda value: (
                    f"{value}  |  @{persona_by_id[value]['handle']}  |  "
                    f"{persona_by_id[value]['marketplace']}"
                ),
            )
            if st.button("Open persona", type="primary"):
                st.session_state["selected_persona_id"] = selected_match
                st.rerun()
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Persona": item["persona_id"],
                            "Handle": item["handle"],
                            "Marketplace": item["marketplace"],
                            "First seen": item["first_seen"],
                            "Last seen": item["last_seen"],
                        }
                        for item in matches
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )

selected_id = st.session_state.get("selected_persona_id")
selected_persona = persona_by_id.get(selected_id)
if selected_id and not selected_persona:
    st.info("The selected persona is outside the current timeline range.")
    selected_id = None

candidate_rows = []
if selected_persona:
    try:
        candidate_rows = get_candidates(
            selected_id,
            top=25,
            since=since,
            until=until,
            api_url=api_url,
        )
    except ApiError as error:
        st.error(f"Could not load candidate matches: {error}")

with tabs[1]:
    if not selected_persona:
        st.info("Select a persona from Search to view candidate matches.")
    else:
        st.subheader(f"Matches for {selected_id}")
        table_rows = [
            {
                "Persona": row["persona"]["persona_id"],
                "Marketplace": row["persona"]["marketplace"],
                "Handle": row["persona"]["handle"],
                "Confidence": format_confidence(row["confidence"]),
                "Tier": row["tier"].upper(),
                "Identity": row["breakdown"].get("identity_graph", 0.0),
                "Infrastructure": row["breakdown"].get("infrastructure", 0.0),
                "Writing style": row["breakdown"].get("stylometry", 0.0),
            }
            for row in candidate_rows
        ]
        st.dataframe(
            pd.DataFrame(table_rows).style.map(
                tier_badge_style,
                subset=["Tier"],
            ),
            hide_index=True,
            use_container_width=True,
        )
        if candidate_rows:
            candidate_ids = [row["persona"]["persona_id"] for row in candidate_rows]
            candidate_id = st.selectbox("Compare candidate", candidate_ids)
            if st.button("Compare", key="compare_candidate"):
                try:
                    comparison = compare_personas(selected_id, candidate_id, api_url=api_url)
                    st.markdown(
                        f"**Tier: {comparison['tier']}** | "
                        f"Confidence {format_confidence(comparison['confidence'])}"
                    )
                    st.write(comparison["explanation"])
                    for signal, evidence in comparison["evidence"].items():
                        with st.expander(signal.replace("_", " ").title()):
                            if evidence:
                                for item in evidence:
                                    st.write(f"- {item}")
                            else:
                                st.write("No evidence recorded.")
                except ApiError as error:
                    st.error(f"Comparison failed: {error}")
        else:
            st.info("No other candidates above the minimum confidence.")

with tabs[2]:
    if not selected_persona:
        st.info("Select a persona from Search to view its profile.")
    else:
        try:
            profile = get_persona(selected_id, api_url=api_url)
            left, right = st.columns([1, 1])
            with left:
                st.subheader(f"{profile['persona_id']} | @{profile['handle']}")
                st.write(f"Marketplace: {profile['marketplace']}")
                st.write(f"First seen: {profile['first_seen']}")
                st.write(f"Last seen: {profile['last_seen']}")
                st.markdown("**Identifiers**")
                st.dataframe(
                    pd.DataFrame(profile.get("identifiers", [])),
                    hide_index=True,
                    use_container_width=True,
                )
            with right:
                st.markdown(f"**Text samples · {len(profile.get('texts', []))}**")
                for index, sample in enumerate(profile.get("texts", []), start=1):
                    with st.expander(f"Sample {index} | {sample['posted_at']}"):
                        st.write(sample["text"])
            links = linked_personas(profile, all_personas)
            st.markdown(f"**Linked personas · {len(links)}**")
            if links:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Persona": link["persona"]["persona_id"],
                                "Handle": link["persona"]["handle"],
                                "Marketplace": link["persona"]["marketplace"],
                                "Shared identifiers": ", ".join(
                                    f"{item['type']}: {item['value']}"
                                    for item in link["shared_identifiers"]
                                ),
                            }
                            for link in links
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.caption("No exact shared identifiers in the available records.")
        except ApiError as error:
            st.error(f"Could not load persona profile: {error}")

with tabs[3]:
    if not selected_persona:
        st.info("Select a persona from Search to view its candidate graph.")
    elif candidate_rows:
        st.plotly_chart(
            build_candidate_graph(selected_persona, candidate_rows[:12]),
            use_container_width=True,
        )
        legend_items = " ".join(
            f'<span style="{tier_badge_style(tier_name)}; padding:0.2rem 0.5rem; '
            f'border-radius:4px; margin-right:0.35rem">{tier_name.upper()} tier edge</span>'
            for tier_name in ("strong", "moderate", "weak")
        )
        st.markdown(legend_items, unsafe_allow_html=True)
        st.caption("Edge labels name the strongest signal; the legend identifies edge tier.")
    else:
        st.info("No candidates to graph in the selected timeline range.")

with tabs[4]:
    if not selected_persona:
        st.info("Select a persona from Search to export its shown candidates.")
    elif candidate_rows:
        st.markdown(f"**Export · {len(candidate_rows)} shown candidates**")
        csv_col, json_col = st.columns(2)
        for output_format, column, mime, label in (
            ("csv", csv_col, "text/csv", "Prepare candidate CSV"),
            ("json", json_col, "application/json", "Prepare candidate JSON"),
        ):
            with column:
                if st.button(label, key=f"prepare_{output_format}"):
                    try:
                        payload, _ = candidate_export_payload(
                            candidate_rows,
                            output_format,
                            since=since,
                            until=until,
                            api_url=api_url,
                        )
                        st.session_state[f"candidate_export_{output_format}"] = payload
                    except ApiError as error:
                        st.error(f"Export failed: {error}")
                payload = st.session_state.get(f"candidate_export_{output_format}")
                if payload:
                    st.download_button(
                        f"Download {output_format.upper()}",
                        data=payload,
                        file_name=f"{selected_id}_candidates.{output_format}",
                        mime=mime,
                        key=f"download_{output_format}",
                    )
    else:
        st.info("No candidates to export in the selected timeline range.")
