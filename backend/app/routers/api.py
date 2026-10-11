"""HTTP endpoints for persona lookup, comparison, candidates, and export."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.entities import Persona
from app.services.storage.graph_store import GraphStore

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: str = Field(min_length=1)
    b: str = Field(min_length=1)


class ComparisonResponse(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    tier: Literal["strong", "moderate", "weak"]
    breakdown: dict[str, float]
    weights_used: dict[str, float]
    evidence: dict[str, list[str]]
    explanation: str


class CandidateResponse(ComparisonResponse):
    persona: Persona


class ExportJSONResponse(BaseModel):
    rows: list[dict]


def _store(request: Request) -> GraphStore:
    return request.app.state.store


def _validate_range(since: datetime | None, until: datetime | None) -> None:
    if since is not None and until is not None:
        since_utc = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since.astimezone(timezone.utc)
        until_utc = until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until.astimezone(timezone.utc)
        if since_utc > until_utc:
            raise HTTPException(status_code=422, detail="since must be earlier than or equal to until")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/personas", response_model=list[Persona])
def list_personas(
    request: Request,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Persona]:
    _validate_range(since, until)
    return _store(request).list_personas(since=since, until=until)


@router.get("/personas/{persona_id}", response_model=Persona)
def get_persona(persona_id: str, request: Request) -> Persona:
    persona = _store(request).get_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.post("/compare", response_model=ComparisonResponse)
def compare_personas(payload: CompareRequest, request: Request) -> dict:
    try:
        return _store(request).compare(payload.a, payload.b)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Persona not found") from error


@router.get("/personas/{persona_id}/candidates", response_model=list[CandidateResponse])
def get_candidates(
    persona_id: str,
    request: Request,
    top: int = Query(default=5, ge=1, le=100),
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    _validate_range(since, until)
    try:
        return _store(request).candidates(
            persona_id,
            top=top,
            since=since,
            until=until,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Persona not found") from error


@router.get("/export")
def export_personas(
    request: Request,
    format: Literal["csv", "json", "report"] = Query(default="json"),
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response:
    _validate_range(since, until)
    rows = _store(request).export_rows(since=since, until=until)
    if format == "json":
        return Response(
            content=ExportJSONResponse(rows=rows).model_dump_json(),
            media_type="application/json",
        )
    if format == "csv":
        output = io.StringIO(newline="")
        columns = [
            "persona_id",
            "marketplace",
            "handle",
            "first_seen",
            "last_seen",
            "identifiers",
            "text_sample_count",
        ]
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "identifiers": "; ".join(
                        f"{item['type']}={item['value']}" for item in row["identifiers"]
                    ),
                }
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=personas.csv"},
        )

    lines = [
        "# Persona Export",
        "",
        "These dataset records are leads for human review, not proof of attribution.",
        "",
        "| Persona | Marketplace | Handle | First seen | Last seen | Identifiers | Text samples |",
        "|---|---|---|---|---|---:|",
    ]
    for row in rows:
        identifiers = ", ".join(
            f"{item['type']}: {item['value']}" for item in row["identifiers"]
        ) or "None"
        cells = [
            row["persona_id"],
            row["marketplace"],
            row["handle"],
            row["first_seen"],
            row["last_seen"],
            identifiers,
            str(row["text_sample_count"]),
        ]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in cells) + " |")
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/markdown")