"""FastAPI application for incident investigation UI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from shared.llm import GeminiClient, loadLlmConfig
from ui.benchmark_overview import loadBenchmarkOverview
from ui.incident_service import (
    BENCHMARK_CASE_IDS,
    FEATURED_CASE_IDS,
    buildCaseMetadata,
    buildCasePreview,
    listBenchmarkCases,
    listDemoCases,
    loadCaseFromBenchmark,
    parseIncidentPayload,
    runIncidentInvestigation,
)
from ui.models import IncidentInvestigationResponse

UI_DIR = Path(__file__).resolve().parent
STATIC_DIR = UI_DIR / "static"

app = FastAPI(
    title="Incident Investigator",
    description="Investigation → Post-Mortem product interface",
    version="1.0.0",
)


class InvestigateBenchmarkRequest(BaseModel):
    case_id: str
    stage: int = Field(default=3, ge=0, le=3)


class InvestigatePayloadRequest(BaseModel):
    case: dict
    stage: int = Field(default=3, ge=0, le=3)


@app.get("/api/health")
def healthCheck():
    config = loadLlmConfig()
    return {
        "status": "ok",
        "model": config.model,
        "provider": config.provider,
        "benchmark_case_count": len(BENCHMARK_CASE_IDS),
        "featured_case_ids": sorted(FEATURED_CASE_IDS),
        "demo_cases": list(BENCHMARK_CASE_IDS),
    }


@app.get("/api/benchmark-cases")
def getBenchmarkCases():
    return [item.model_dump() for item in listBenchmarkCases()]


@app.get("/api/demo-cases")
def getDemoCases():
    return [item.model_dump() for item in listDemoCases()]


@app.get("/api/benchmark-overview")
def getBenchmarkOverview():
    overview = loadBenchmarkOverview()
    if overview is None:
        raise HTTPException(status_code=404, detail="Benchmark evaluation summary not available")
    return overview.model_dump()


@app.get("/api/cases/{case_id}/preview")
def previewCase(case_id: str):
    try:
        case = loadCaseFromBenchmark(case_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return buildCaseMetadata(case).model_dump()


@app.post("/api/investigate/benchmark", response_model=IncidentInvestigationResponse)
def investigateBenchmark(request: InvestigateBenchmarkRequest):
    try:
        case = loadCaseFromBenchmark(request.case_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    client = GeminiClient()
    try:
        return runIncidentInvestigation(case, client, investigationStage=request.stage)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/investigate/payload", response_model=IncidentInvestigationResponse)
def investigatePayload(request: InvestigatePayloadRequest):
    try:
        case = parseIncidentPayload(request.case)
    except (ValueError, ValidationError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    client = GeminiClient()
    try:
        return runIncidentInvestigation(case, client, investigationStage=request.stage)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    faviconPath = STATIC_DIR / "favicon.svg"
    if not faviconPath.exists():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(faviconPath, media_type="image/svg+xml")


@app.get("/")
def serveLanding():
    landingPath = STATIC_DIR / "landing.html"
    if not landingPath.exists():
        raise HTTPException(status_code=404, detail="Landing page not built")
    return FileResponse(landingPath)


@app.get("/investigate")
def serveInvestigate():
    investigatePath = STATIC_DIR / "investigate.html"
    if not investigatePath.exists():
        raise HTTPException(status_code=404, detail="Investigation UI not built")
    return FileResponse(investigatePath)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
