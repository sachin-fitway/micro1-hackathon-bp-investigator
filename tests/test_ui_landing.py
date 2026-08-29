"""Tests for landing page and routing."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ui.app import app


@pytest.fixture
def client():
    return TestClient(app)


def testLandingPageRoute(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Find what failed." in response.text
    assert "Prove why." in response.text
    assert "11 logs" in response.text
    assert "inventory_reserve" in response.text
    assert "/investigate" in response.text


def testFaviconRoute(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "image" in response.headers.get("content-type", "")
    assert b"svg" in response.content[:256].lower()


def testInvestigatePageRoute(client):
    response = client.get("/investigate")
    assert response.status_code == 200
    assert "What do you want to investigate?" in response.text
    assert 'id="investigate-btn"' in response.text


def testLandingPageStructure():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "landing.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert "Give us distributed-system logs" in html
    assert 'id="how-it-works"' in html
    assert 'id="evidence-first"' in html
    assert "Try Now →" in html
    assert "89.73%" not in html
    assert "Mean IQS" in html
    assert "15-case development benchmark" in html
    assert "Not a claim of universal accuracy" in html
    assert "Built to be evaluated" in html
    assert "lp-hero-story" in html
    assert "lp-contrast-featured" in html
    assert "lp-proof-headline" in html


def testInvestigatePageStructure():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert 'id="benchmark-case-grid"' in html
    assert "Investigate Incident" in html
    assert 'href="/"' in html


def testApiEndpointsStillWorkFromLandingContext(client):
    assert client.get("/api/benchmark-cases").status_code == 200
    assert client.get("/api/cases/case_01/preview").status_code == 200
    assert len(client.get("/api/benchmark-cases").json()) == 15
