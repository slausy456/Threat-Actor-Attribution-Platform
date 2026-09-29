"""
Streamlit dashboard — search, actor profile, graph view, confidence
visualization, CSV/JSON export. See docs/architecture.md.
"""
import streamlit as st

st.set_page_config(page_title="Threat Actor Attribution Platform", layout="wide")

st.title("Threat Actor Attribution Platform")
st.caption(
    "Multi-signal, confidence-scored attribution — built on legal, published "
    "research datasets only. See docs/ethics_and_data_sources.md."
)

st.info("Dashboard scaffold — wire up to the FastAPI backend as each pillar lands.")

tab_search, tab_profile, tab_graph, tab_export = st.tabs(
    ["Search", "Actor Profile", "Graph View", "Export"]
)

with tab_search:
    st.text_input("Search identifiers (handle, PGP key fragment, wallet...)")

with tab_profile:
    st.write("Actor profile view: identifiers, linked personas, confidence breakdown.")

with tab_graph:
    st.write("Identity relationship graph view (Neo4j-backed).")

with tab_export:
    st.write("Export result set as CSV / JSON / report.")
