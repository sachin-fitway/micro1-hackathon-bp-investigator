"""Tests for benchmark case browser and overview API."""

from __future__ import annotations

import json

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shared.case_loader import BENCHMARK_CASE_IDS
from ui.app import app
from ui.benchmark_overview import loadBenchmarkOverview
from ui.incident_service import FEATURED_CASE_IDS, listBenchmarkCases


@pytest.fixture
def client():
    return TestClient(app)


FORBIDDEN_RESPONSE_KEYS = frozenset({
    "ground_truth",
    "failure_pattern",
    "decoy_diagnosis",
    "baseline_hypothesis",
    "difficulty_factors",
})


def testListBenchmarkCasesReturnsAllFifteen():
    summaries = listBenchmarkCases()
    caseIds = [item.case_id for item in summaries]
    assert caseIds == list(BENCHMARK_CASE_IDS)
    assert len(summaries) == 15


def testBenchmarkCasesEndpointReturnsAllFifteen(client):
    response = client.get("/api/benchmark-cases")
    assert response.status_code == 200
    payload = response.json()
    caseIds = [item["case_id"] for item in payload]
    assert caseIds == [f"case_{index:02d}" for index in range(1, 16)]


def testDemoCasesEndpointMatchesBenchmarkCases(client):
    benchmark = client.get("/api/benchmark-cases").json()
    demo = client.get("/api/demo-cases").json()
    assert benchmark == demo


def testFeaturedCasesAreSubsetOfBenchmarkCases():
    summaries = listBenchmarkCases()
    featured = {item.case_id for item in summaries if item.is_featured}
    assert featured == set(FEATURED_CASE_IDS)
    assert len(featured) == 4


@pytest.mark.parametrize("case_id", [f"case_{index:02d}" for index in range(1, 16)])
def testPreviewEndpointWorksForAllBenchmarkCases(client, case_id: str):
    response = client.get(f"/api/cases/{case_id}/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert "process_name" in body
    assert "ground_truth" not in body


def testBenchmarkCaseResponsesDoNotLeakGroundTruth(client):
    response = client.get("/api/benchmark-cases")
    serialized = json.dumps(response.json()).lower()
    for key in FORBIDDEN_RESPONSE_KEYS:
        assert f'"{key}"' not in serialized


def testHealthEndpointReportsBenchmarkCount(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_case_count"] == 15
    assert len(body["demo_cases"]) == 15


def testBenchmarkOverviewEndpoint(client):
    overview = loadBenchmarkOverview()
    if overview is None:
        pytest.skip("eval_submission.json not available")
    response = client.get("/api/benchmark-overview")
    assert response.status_code == 200
    body = response.json()
    assert body["case_count"] == 15
    assert body["stage_0_iqs_percent"] == pytest.approx(89.06, abs=0.1)
    assert body["stage_3_iqs_percent"] == pytest.approx(89.73, abs=0.1)
    assert body["delta_pp"] == pytest.approx(0.67, abs=0.1)
    metricLabels = {row["label"] for row in body["metrics"]}
    assert "Divergence accuracy" in metricLabels
    assert "No-fabrication" in metricLabels
    assert "prediction" not in body


def testProductUxStructurePresent():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert "What do you want to investigate?" in html
    assert 'id="case-select"' in html
    assert "Benchmark Incidents" in html
    assert 'id="evaluation-view"' in html
    assert "Show investigation process" in html
    assert 'id="view-postmortem-btn"' in html
    assert "Featured shortcuts" not in html
    assert 'id="health-badge"' not in html


def testBenchmarkOverviewHtmlSectionPresent():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert 'id="benchmark-case-grid"' in html
    assert "Benchmark Incidents" in html
    assert 'id="benchmark-overview"' in html
    assert "Benchmark Results" in html
