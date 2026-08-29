"""Submission-readiness tests: failure handling, security, immutability, grounding."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agents.post_mortem_reporter import REQUIRED_POST_MORTEM_SECTIONS
from generate_data import buildCases
from shared.schemas import InvestigationResult, PostMortemReport, RootCauseCategory
from ui.app import app
from ui.incident_service import (
    buildCaseMetadata,
    buildCausalChain,
    buildHydratedLogEntries,
    loadCaseFromBenchmark,
    parseIncidentPayload,
    runIncidentInvestigation,
)
from ui.models import IncidentInvestigationResponse, PipelinePhase
from ui.story_formatter import buildIncidentStory


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
        explanation="Skipped reservation.",
    )


def _sampleMarkdown(diagnosis: InvestigationResult) -> str:
    culprit = diagnosis.culprit_log_ids[0]
    evidence = diagnosis.evidence_log_ids[-1]
    return "\n\n".join(
        f"## {title}\nReferences {culprit} and {evidence}."
        for title in REQUIRED_POST_MORTEM_SECTIONS
    )


class MockLlmClient:
    def __init__(self, diagnosis: InvestigationResult, *, fail: bool = False):
        self.diagnosis = diagnosis
        self.fail = fail

    def completeJson(self, prompt, modelClass, stage="unknown"):
        from shared.llm import LlmCallResult

        if self.fail:
            raise RuntimeError("LLM provider timeout")
        if modelClass is PostMortemReport:
            return LlmCallResult(
                parsed=PostMortemReport(markdown=_sampleMarkdown(self.diagnosis)),
                raw_response="{}",
                retry_count=0,
            )
        if modelClass is InvestigationResult:
            return LlmCallResult(
                parsed=self.diagnosis,
                raw_response="{}",
                retry_count=0,
            )
        raise AssertionError(f"Unexpected model: {modelClass}")


class IncompleteReporterClient(MockLlmClient):
    def completeJson(self, prompt, modelClass, stage="unknown"):
        from shared.llm import LlmCallResult

        if modelClass is PostMortemReport:
            return LlmCallResult(
                parsed=PostMortemReport(markdown="## Executive Summary\nToo short."),
                raw_response="{}",
                retry_count=0,
            )
        return super().completeJson(prompt, modelClass, stage=stage)


def testPathTraversalRejected():
    with pytest.raises(FileNotFoundError):
        loadCaseFromBenchmark("../../etc/passwd")


def testInvalidBenchmarkCaseReturns404():
    client = TestClient(app)
    response = client.get("/api/cases/case_99/preview")
    assert response.status_code == 404


def testMalformedPayloadMissingLogsReturns400():
    client = TestClient(app)
    response = client.post(
        "/api/investigate/payload",
        json={"case": {"case_id": "x", "process_context": {"process_name": "p", "expected_sequence": []}, "raw_logs": []}, "stage": 3},
    )
    assert response.status_code == 400


def testMalformedPayloadInvalidLogShapeReturns400():
    client = TestClient(app)
    response = client.post(
        "/api/investigate/payload",
        json={
            "case": {
                "case_id": "x",
                "process_context": {"process_name": "p", "expected_sequence": ["step_a"]},
                "raw_logs": [{"log_id": "x-01"}],
            },
            "stage": 3,
        },
    )
    assert response.status_code == 400


def testInvestigateBenchmarkLlmFailureReturns500(case01, case01Diagnosis):
    client = TestClient(app)
    with patch("ui.app.runIncidentInvestigation") as mockRun:
        mockRun.side_effect = RuntimeError("LLM provider timeout")
        response = client.post(
            "/api/investigate/benchmark",
            json={"case_id": "case_01", "stage": 3},
        )
    assert response.status_code == 500
    assert "timeout" in response.json()["detail"].lower()


def testIncompleteReporterOutputRaises(case01, case01Diagnosis):
    client = IncompleteReporterClient(case01Diagnosis)
    with patch("ui.incident_service.runWorkflowFull", return_value=case01Diagnosis):
        with pytest.raises(ValueError, match="missing required sections"):
            runIncidentInvestigation(case01, client, investigationStage=3)


def testUiResponseDiagnosisMatchesWorkflowOutput(case01, case01Diagnosis):
    client = MockLlmClient(case01Diagnosis)
    with patch("ui.incident_service.runWorkflowFull", return_value=case01Diagnosis) as mockWorkflow:
        result = runIncidentInvestigation(case01, client, investigationStage=3)
    workflowDiagnosis = mockWorkflow.return_value
    assert result.diagnosis.divergence_step == workflowDiagnosis.divergence_step
    assert result.diagnosis.root_cause_category == workflowDiagnosis.root_cause_category
    assert result.diagnosis.culprit_log_ids == workflowDiagnosis.culprit_log_ids
    assert result.diagnosis.evidence_log_ids == workflowDiagnosis.evidence_log_ids


def testHydratedLogIdsExistInSourceLogs(case01, case01Diagnosis):
    entries = buildHydratedLogEntries(case01, case01Diagnosis)
    sourceIds = {log.log_id for log in case01.raw_logs}
    for entry in entries:
        if entry.role in ("culprit", "evidence", "culprit+evidence"):
            assert entry.log_id in sourceIds


def testUiLayerRejectsMutatedArtifact(case01, case01Diagnosis):
    from shared.schemas import PostMortemArtifact

    mutatedDiagnosis = case01Diagnosis.model_copy(update={"culprit_log_ids": ["c01-03"]})
    fakeArtifact = PostMortemArtifact(
        case_id=case01.case_id,
        diagnosis=mutatedDiagnosis,
        markdown="## Executive Summary\nTest",
        retrieved_evidence_log_ids=["c01-02"],
        retrieved_culprit_log_ids=["c01-03"],
        unknown_log_ids=[],
        claim_traces=[],
        evidence_table_markdown="",
        investigation_stage=3,
    )
    with patch("ui.incident_service.runWorkflowFull", return_value=case01Diagnosis):
        with patch("ui.incident_service.runPostMortemReporter", return_value=fakeArtifact):
            with pytest.raises(ValueError, match="culprit_log_ids"):
                runIncidentInvestigation(case01, MockLlmClient(case01Diagnosis), investigationStage=3)


def testExportJsonContainsOnlyResponseFields(case01, case01Diagnosis):
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    causal = buildCausalChain(case01, case01Diagnosis)
    story = buildIncidentStory(metadata, case01Diagnosis, hydrated, [], causal, True)
    response = IncidentInvestigationResponse(
        case_id=case01.case_id,
        metadata=metadata,
        diagnosis=case01Diagnosis,
        diagnosis_integrity_verified=True,
        story=story,
        phases=[PipelinePhase(phase_id="logs", title="Logs", status="complete", details=[])],
        hydrated_logs=hydrated,
        claim_traces=[],
        causal_chain=causal,
        post_mortem_markdown="## Executive Summary\nTest.",
        evidence_table_markdown="| Log | Role |",
        unknown_log_ids=[],
        investigation_stage=3,
    )
    payload = json.loads(response.model_dump_json())
    assert "ground_truth" not in payload
    assert "meta" not in payload
    assert payload["diagnosis"]["divergence_step"] == "inventory_reserve"


@pytest.mark.parametrize("case_id", ["case_01", "case_11", "case_14", "case_15"])
def testApiPipelineDiagnosisMatchesArtifact(case_id: str):
    """Verify UI service preserves diagnosis when workflow returns artifact diagnosis."""
    case = loadCaseFromBenchmark(case_id)
    artifactsDir = Path(__file__).resolve().parent.parent / "reports" / "artifacts"
    artifactPath = artifactsDir / f"{case_id}_post_mortem.json"
    if not artifactPath.exists():
        pytest.skip(f"Missing artifact: {artifactPath}")
    stored = json.loads(artifactPath.read_text(encoding="utf-8"))
    diagnosis = InvestigationResult.model_validate(stored["diagnosis"])
    client = MockLlmClient(diagnosis)

    with patch("ui.incident_service.runWorkflowFull", return_value=diagnosis):
        result = runIncidentInvestigation(case, client, investigationStage=3)

    assert result.diagnosis.divergence_step == stored["diagnosis"]["divergence_step"]
    assert result.diagnosis.root_cause_category.value == stored["diagnosis"]["root_cause_category"]
    assert result.diagnosis.culprit_log_ids == stored["diagnosis"]["culprit_log_ids"]


def testParseIncidentPayloadRejectsMissingSequence(case01):
    payload = {
        "case_id": "upload",
        "process_context": {"process_name": "test", "expected_sequence": []},
        "raw_logs": [log.model_dump() for log in case01.raw_logs[:1]],
    }
    with pytest.raises(ValueError, match="expected_sequence"):
        parseIncidentPayload(payload)
