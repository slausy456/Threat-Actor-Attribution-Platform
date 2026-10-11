"""Plain API and presentation-data helpers for the Streamlit dashboard."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, time
from urllib.parse import urlparse

import networkx as nx
import plotly.graph_objects as go
import requests

DEFAULT_API_URL = "http://127.0.0.1:8000"
ALLOWED_API_HOSTS = {"127.0.0.1", "localhost", "::1"}
TIER_COLORS = {"strong": "#12623a", "moderate": "#795000", "weak": "#555555"}
TIER_TEXT_COLOR = "#ffffff"
SIGNAL_LABELS = {
    "identity_graph": "Identity graph",
    "infrastructure": "Infrastructure",
    "stylometry": "Writing style",
}


class ApiError(RuntimeError):
    """Raised when the local attribution API cannot serve a dashboard request."""


def tier_badge_style(tier: str) -> str:
    """Return high-contrast badge CSS; the visible tier word carries meaning too."""
    color = TIER_COLORS.get(str(tier).lower(), TIER_COLORS["weak"])
    return (
        f"color: {TIER_TEXT_COLOR}; background-color: {color}; "
        "font-weight: 700; border: 1px solid #ffffff;"
    )


def format_confidence(confidence: float) -> str:
    return f"{float(confidence):.3f}"


def timeline_filter_bounds(selection) -> tuple[datetime | None, datetime | None]:
    if not isinstance(selection, (tuple, list)) or len(selection) != 2:
        return None, None
    start, end = selection
    if not isinstance(start, date) or not isinstance(end, date):
        return None, None
    since = datetime.combine(start, time.min)
    until = datetime.combine(end, time.max).replace(microsecond=0)
    return since, until


def api_base_url(value: str | None = None) -> str:
    base = (value or os.getenv("ATTRIBUTION_API_URL") or DEFAULT_API_URL).rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in ALLOWED_API_HOSTS:
        raise ValueError("ATTRIBUTION_API_URL must point to a local HTTP API host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ATTRIBUTION_API_URL must be a plain local base URL")
    return base


def _date_value(value: date | datetime | str | None, end_of_day: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        stamp = time.max if end_of_day else time.min
        return datetime.combine(value, stamp).isoformat(timespec="seconds")
    return str(value)


def _timeline_params(since=None, until=None) -> dict[str, str]:
    params = {}
    since_value = _date_value(since)
    until_value = _date_value(until, end_of_day=True)
    if since_value:
        params["since"] = since_value
    if until_value:
        params["until"] = until_value
    return params


def _request(method: str, path: str, api_url: str | None = None, **kwargs):
    url = f"{api_base_url(api_url)}{path}"
    try:
        response = requests.request(method, url, timeout=8, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as error:
        raise ApiError(f"Local API request failed: {error}") from error


def list_personas(since=None, until=None, api_url: str | None = None) -> list[dict]:
    response = _request(
        "GET",
        "/personas",
        api_url,
        params=_timeline_params(since, until),
    )
    return response.json()


def get_persona(persona_id: str, api_url: str | None = None) -> dict:
    return _request("GET", f"/personas/{persona_id}", api_url).json()


def get_candidates(
    persona_id: str,
    top: int = 20,
    since=None,
    until=None,
    api_url: str | None = None,
) -> list[dict]:
    params = {"top": top, **_timeline_params(since, until)}
    return _request(
        "GET",
        f"/personas/{persona_id}/candidates",
        api_url,
        params=params,
    ).json()


def compare_personas(a: str, b: str, api_url: str | None = None) -> dict:
    return _request("POST", "/compare", api_url, json={"a": a, "b": b}).json()


def search_personas(query: str, personas: list[dict]) -> list[dict]:
    needle = query.strip().casefold()
    if not needle:
        return []
    found = []
    for persona in personas:
        identifier_values = [item.get("value", "") for item in persona.get("identifiers", [])]
        haystack = [persona.get("persona_id", ""), persona.get("handle", ""), *identifier_values]
        if any(needle in str(value).casefold() for value in haystack):
            found.append(persona)
    return found


def filter_personas_by_timeline(personas: list[dict], since=None, until=None) -> list[dict]:
    lower = _date_value(since)
    upper = _date_value(until, end_of_day=True)
    return [
        persona
        for persona in personas
        if (not lower or persona.get("last_seen", "") >= lower)
        and (not upper or persona.get("first_seen", "") <= upper)
    ]


def linked_personas(persona: dict, personas: list[dict]) -> list[dict]:
    own = {
        (identifier.get("type"), identifier.get("value"))
        for identifier in persona.get("identifiers", [])
    }
    links = []
    for candidate in personas:
        if candidate.get("persona_id") == persona.get("persona_id"):
            continue
        shared = sorted(
            own
            & {
                (identifier.get("type"), identifier.get("value"))
                for identifier in candidate.get("identifiers", [])
            }
        )
        if shared:
            links.append(
                {
                    "persona": candidate,
                    "shared_identifiers": [
                        {"type": identifier_type, "value": value}
                        for identifier_type, value in shared
                    ],
                }
            )
    return sorted(links, key=lambda item: item["persona"].get("persona_id", ""))


def _strongest_signal(candidate: dict) -> str:
    breakdown = candidate.get("breakdown", {})
    if not breakdown:
        return "No signal"
    signal = max(breakdown, key=breakdown.get)
    return SIGNAL_LABELS.get(signal, signal.replace("_", " ").title())


def build_candidate_graph(persona: dict, candidates: list[dict]) -> go.Figure:
    graph = nx.Graph()
    root_id = persona["persona_id"]
    graph.add_node(root_id, label=f"{root_id} SELECTED", tier="selected")
    for candidate in candidates:
        candidate_persona = candidate["persona"]
        candidate_id = candidate_persona["persona_id"]
        graph.add_node(
            candidate_id,
            label=f"{candidate_id} {format_confidence(candidate['confidence'])}",
            tier=candidate.get("tier", "weak"),
        )
        graph.add_edge(
            root_id,
            candidate_id,
            label=_strongest_signal(candidate),
            tier=candidate.get("tier", "weak"),
        )

    positions = nx.spring_layout(graph, seed=19, k=1.15)
    figure = go.Figure()
    for tier_name in ("strong", "moderate", "weak"):
        edge_x, edge_y = [], []
        for source, target, attributes in graph.edges(data=True):
            if attributes["tier"] != tier_name:
                continue
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            figure.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                text=attributes["label"],
                showarrow=False,
                bgcolor=TIER_COLORS[tier_name],
                bordercolor=TIER_COLORS[tier_name],
                font={"size": 11, "color": TIER_TEXT_COLOR},
                borderpad=4,
            )
        for outline_color, outline_width in (("#ffffff", 8), ("#000000", 6)):
            figure.add_trace(
                go.Scatter(
                    x=edge_x,
                    y=edge_y,
                    mode="lines",
                    line={"color": outline_color, "width": outline_width},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        figure.add_trace(
            go.Scatter(
                x=edge_x,
                y=edge_y,
                mode="lines",
                line={"color": TIER_COLORS[tier_name], "width": 3},
                hoverinfo="skip",
                showlegend=False,
            )
            )

    for tier_name in ("selected", "strong", "moderate", "weak"):
        node_ids = [node for node, attrs in graph.nodes(data=True) if attrs["tier"] == tier_name]
        if not node_ids:
            continue
        color = "#174a7e" if tier_name == "selected" else TIER_COLORS[tier_name]
        figure.add_trace(
            go.Scatter(
                x=[positions[node][0] for node in node_ids],
                y=[positions[node][1] for node in node_ids],
                mode="markers",
                marker={"size": 22 if tier_name == "selected" else 17, "color": color},
                name="Selected" if tier_name == "selected" else tier_name.title(),
                hovertemplate="%{text}<extra></extra>",
                text=[graph.nodes[node]["label"] for node in node_ids],
                hoverlabel={"bgcolor": color, "font": {"color": TIER_TEXT_COLOR}},
                showlegend=False,
            )
        )
        for node in node_ids:
            figure.add_annotation(
                x=positions[node][0],
                y=positions[node][1],
                text=graph.nodes[node]["label"],
                showarrow=False,
                bgcolor=color,
                bordercolor=TIER_TEXT_COLOR,
                borderwidth=1,
                borderpad=5,
                font={"size": 11, "color": TIER_TEXT_COLOR},
            )
    figure.update_layout(
        height=560,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False},
        yaxis={"visible": False},
        showlegend=False,
    )
    return figure


def candidate_export_payload(
    candidates: list[dict],
    output_format: str,
    since=None,
    until=None,
    api_url: str | None = None,
) -> tuple[str, str]:
    if output_format not in {"csv", "json"}:
        raise ValueError("output_format must be csv or json")
    export_data = _request(
        "GET",
        "/export",
        api_url,
        params={"format": "json", **_timeline_params(since, until)},
    ).json()
    exported_by_id = {row["persona_id"]: row for row in export_data.get("rows", [])}
    rows = []
    for candidate in candidates:
        persona = candidate["persona"]
        base = exported_by_id.get(persona["persona_id"], {})
        breakdown = candidate.get("breakdown", {})
        evidence = candidate.get("evidence", {})
        rows.append(
            {
                "persona_id": persona["persona_id"],
                "marketplace": base.get("marketplace", persona.get("marketplace", "")),
                "handle": base.get("handle", persona.get("handle", "")),
                "first_seen": base.get("first_seen", persona.get("first_seen", "")),
                "last_seen": base.get("last_seen", persona.get("last_seen", "")),
                "identifiers": base.get("identifiers", persona.get("identifiers", [])),
                "confidence": candidate.get("confidence"),
                "tier": candidate.get("tier", "weak"),
                "identity_graph": breakdown.get("identity_graph", 0.0),
                "infrastructure": breakdown.get("infrastructure", 0.0),
                "stylometry": breakdown.get("stylometry", 0.0),
                "evidence": evidence,
                "explanation": candidate.get("explanation", ""),
            }
        )
    if output_format == "json":
        return json.dumps(rows, indent=2), "application/json"

    buffer = io.StringIO(newline="")
    columns = [
        "persona_id", "marketplace", "handle", "first_seen", "last_seen",
        "confidence", "tier", "identity_graph", "infrastructure", "stylometry",
        "identifiers", "evidence", "explanation",
    ]
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                **row,
                "identifiers": json.dumps(row["identifiers"]),
                "evidence": json.dumps(row["evidence"]),
            }
        )
    return buffer.getvalue(), "text/csv"
