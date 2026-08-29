"""UI and integration tests for incident investigation interface."""

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
    buildCausalChain,
    buildCaseMetadata,
    buildHydratedLogEntries,
    loadArtifactDiagnosis,
    parseIncidentPayload,
    runIncidentInvestigation,
)
from ui.story_formatter import buildIncidentStory
from ui.trace_parser import buildPipelinePhases


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
    def __init__(self, diagnosis: InvestigationResult):
        self.diagnosis = diagnosis

    def completeJson(self, prompt, modelClass, stage="unknown"):
        from shared.llm import LlmCallResult

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


def testBuildCaseMetadata(case01):
    metadata = buildCaseMetadata(case01)
    assert metadata.case_id == "case_01"
    assert metadata.process_name == "ecommerce_checkout"
    assert metadata.log_count == len(case01.raw_logs)


def testParseIncidentPayload(case01):
    payload = {
        "case_id": "upload_01",
        "process_context": case01.process_context.model_dump(),
        "raw_logs": [log.model_dump() for log in case01.raw_logs],
    }
    parsed = parseIncidentPayload(payload)
    assert parsed.case_id == "upload_01"
    assert len(parsed.raw_logs) == len(case01.raw_logs)


def testBuildCausalChainMarksDivergence(case01, case01Diagnosis):
    chain = buildCausalChain(case01, case01Diagnosis)
    divergenceNodes = [node for node in chain if node.is_divergence]
    assert len(divergenceNodes) == 1
    assert divergenceNodes[0].step == "inventory_reserve"


def testRunIncidentInvestigationPreservesDiagnosis(case01, case01Diagnosis):
    client = MockLlmClient(case01Diagnosis)

    with patch("ui.incident_service.runWorkflowFull", return_value=case01Diagnosis):
        result = runIncidentInvestigation(case01, client, investigationStage=3)

    assert result.diagnosis.divergence_step == case01Diagnosis.divergence_step
    assert result.diagnosis.culprit_log_ids == case01Diagnosis.culprit_log_ids
    assert result.diagnosis_integrity_verified
    assert result.post_mortem_markdown
    assert result.claim_traces
    assert result.story.headline
    assert result.story.process_steps
    assert any(phase.phase_id == "evidence_retrieval" for phase in result.phases)


def testHealthEndpoint():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["benchmark_case_count"] == 15


def testDemoCasesEndpoint():
    client = TestClient(app)
    response = client.get("/api/demo-cases")
    assert response.status_code == 200
    caseIds = [item["case_id"] for item in response.json()]
    assert caseIds == [f"case_{index:02d}" for index in range(1, 16)]


def testPreviewEndpoint(case01):
    client = TestClient(app)
    response = client.get("/api/cases/case_01/preview")
    assert response.status_code == 200
    assert response.json()["process_name"] == "ecommerce_checkout"


def testInvestigateBenchmarkMocked(case01, case01Diagnosis):
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    causal = buildCausalChain(case01, case01Diagnosis)
    story = buildIncidentStory(metadata, case01Diagnosis, hydrated, [], causal, True)
    from ui.models import IncidentInvestigationResponse, PipelinePhase

    mockResponse = IncidentInvestigationResponse(
        case_id=case01.case_id,
        metadata=metadata,
        diagnosis=case01Diagnosis,
        diagnosis_integrity_verified=True,
        story=story,
        phases=[PipelinePhase(phase_id="logs", title="Logs", status="complete", details=[])],
        hydrated_logs=hydrated,
        claim_traces=[],
        causal_chain=causal,
        post_mortem_markdown="## Executive Summary\nTest report.",
        evidence_table_markdown="| Log ID | Role |",
        unknown_log_ids=[],
        investigation_stage=3,
    )
    client = TestClient(app)

    with patch("ui.app.runIncidentInvestigation", return_value=mockResponse):
        response = client.post(
            "/api/investigate/benchmark",
            json={"case_id": "case_01", "stage": 3},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["diagnosis"]["divergence_step"] == "inventory_reserve"


def testBuildPipelinePhasesFromTrajectory(tmp_path, case01Diagnosis):
    investigationPath = tmp_path / "case_01_stage3.jsonl"
    postMortemPath = tmp_path / "case_01_stagepost_mortem.jsonl"
    investigationPath.write_text(
        "\n".join([
            json.dumps({
                "step": 1,
                "agent": "preprocess",
                "event": "timeline_built",
                "output": {"log_count": 11},
                "feedback": "",
            }),
            json.dumps({
                "step": 3,
                "agent": "baseline",
                "event": "llm_response",
                "output": case01Diagnosis.model_dump(mode="json"),
                "feedback": "",
            }),
            json.dumps({
                "step": 9,
                "agent": "verifier",
                "event": "adjudication_complete",
                "output": {
                    "decision": "keep_baseline",
                    "confidence": 0.9,
                    "deterministic_blocks": ["DECOY_DEFENSE: example"],
                    "comparison": {"why_selected": "Baseline kept."},
                },
                "feedback": "",
            }),
        ]),
        encoding="utf-8",
    )
    postMortemPath.write_text(
        json.dumps({
            "step": 1,
            "agent": "post_mortem_reporter",
            "event": "logs_retrieved",
            "output": {"retrieved_evidence": ["c01-02"], "retrieved_culprits": ["c01-02"]},
            "feedback": "",
        }) + "\n" + json.dumps({
            "step": 2,
            "agent": "post_mortem_reporter",
            "event": "report_generated",
            "output": {"markdown_length": 1200},
            "feedback": "",
        }),
        encoding="utf-8",
    )
    phases = buildPipelinePhases(investigationPath, postMortemPath)
    assert len(phases) == 5
    assert phases[0].status == "complete"
    assert phases[3].phase_id == "evidence_retrieval"


@pytest.mark.parametrize("case_id", ["case_01", "case_11", "case_14", "case_15"])
def testArtifactDiagnosisMatchesReport(case_id: str):
    artifactsDir = Path(__file__).resolve().parent.parent / "reports" / "artifacts"
    artifactPath = artifactsDir / f"{case_id}_post_mortem.json"
    if not artifactPath.exists():
        pytest.skip(f"Demo artifact missing: {artifactPath}")
    payload = json.loads(artifactPath.read_text(encoding="utf-8"))
    diagnosis = loadArtifactDiagnosis(case_id, artifactsDir)
    assert diagnosis.divergence_step == payload["diagnosis"]["divergence_step"]
    assert diagnosis.root_cause_category.value == payload["diagnosis"]["root_cause_category"]
    assert diagnosis.culprit_log_ids == payload["diagnosis"]["culprit_log_ids"]
