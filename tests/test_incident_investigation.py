"""Tests for end-to-end incident investigation → post-mortem flow."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from generate_data import buildCases
from incident_investigation import runIncidentFlow
from shared.schemas import InvestigationResult, RootCauseCategory


def _samplePostMortemMarkdown(diagnosis: InvestigationResult) -> str:
    culprit = diagnosis.culprit_log_ids[0]
    evidence = diagnosis.evidence_log_ids[-1]
    sections = [
        "Executive Summary",
        "What Happened",
        "Incident Timeline",
        "Root Cause",
        "Detected Divergence",
        "Causal Chain",
        "Impact",
        "Recommended Remediation",
        "Confidence & Limitations",
    ]
    return "\n\n".join(
        f"## {title}\nReferences {culprit} and {evidence}."
        for title in sections
    )


class MockLlmClient:
    def __init__(self, investigation: InvestigationResult):
        self.investigation = investigation
        self.calls: list[str] = []

    def completeJson(self, prompt, modelClass, stage="unknown"):
        from shared.llm import LlmCallResult
        from shared.schemas import PostMortemReport

        self.calls.append(stage)
        if stage == "post_mortem_reporter":
            return LlmCallResult(
                parsed=PostMortemReport(markdown=_samplePostMortemMarkdown(self.investigation)),
                raw_response="{}",
                retry_count=0,
            )
        raise AssertionError(f"Unexpected LLM stage in mock: {stage}")


@pytest.fixture
def case01():
    return next(item for item in buildCases() if item.case_id == "case_01")


@pytest.fixture
def case01Diagnosis():
    return InvestigationResult(
        divergence_step="inventory_reserve",
        root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
        culprit_log_ids=["c01-02"],
        evidence_log_ids=["c01-02", "c01-03"],
        explanation="Reservation skipped.",
    )


def testIncidentFlowPreservesDiagnosisThroughPostMortem(case01, case01Diagnosis, tmp_path):
    mockClient = MockLlmClient(case01Diagnosis)

    def fakeRunner(case, client):
        return case01Diagnosis

    with patch("incident_investigation.STAGE_RUNNERS", {3: fakeRunner}):
        result = runIncidentFlow(case01, mockClient, investigationStage=3, outputDir=tmp_path)

    assert result.investigation.diagnosis.divergence_step == "inventory_reserve"
    assert result.post_mortem.diagnosis.divergence_step == "inventory_reserve"
    assert result.post_mortem.diagnosis.culprit_log_ids == ["c01-02"]
    assert result.report_path.exists()
    assert result.artifact_path.exists()
    content = result.report_path.read_text(encoding="utf-8")
    assert "## Evidence" in content
    assert "## Evidence Trace" in content
    assert "post_mortem_reporter" in mockClient.calls


def testIncidentFlowArtifactJsonContainsClaimTraces(case01, case01Diagnosis, tmp_path):
    mockClient = MockLlmClient(case01Diagnosis)

    with patch("incident_investigation.STAGE_RUNNERS", {3: lambda case, client: case01Diagnosis}):
        result = runIncidentFlow(case01, mockClient, investigationStage=3, outputDir=tmp_path)

    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert payload["diagnosis"]["divergence_step"] == "inventory_reserve"
    assert payload["claim_traces"]
    assert payload["retrieved_evidence_log_ids"]
