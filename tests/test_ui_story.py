"""Tests for incident story presentation layer."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from generate_data import buildCases
from shared.schemas import InvestigationResult, RootCauseCategory
from ui.incident_service import (
    buildCaseMetadata,
    buildCausalChain,
    buildHydratedLogEntries,
    loadCaseFromBenchmark,
)
from ui.models import PipelinePhase, TraceStepDetail
from ui.story_formatter import (
    LOADER_PHASE_COPY,
    buildEvidenceMechanismChain,
    buildFailureTitle,
    buildIncidentStory,
    buildIncidentSummary,
    buildStoryPhases,
    buildWhyItFailed,
    buildWhyBrief,
    describeCategory,
)


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
        explanation="The inventory_reserve step was skipped. Payment authorization failed downstream.",
    )


@pytest.fixture
def case14():
    return loadCaseFromBenchmark("case_14")


@pytest.fixture
def case14Diagnosis():
    artifactPath = Path(__file__).resolve().parent.parent / "reports" / "artifacts" / "case_14_post_mortem.json"
    if not artifactPath.exists():
        pytest.skip("case_14 artifact missing")
    payload = json.loads(artifactPath.read_text(encoding="utf-8"))
    return InvestigationResult.model_validate(payload["diagnosis"])


def testLoaderPhasesDefinedInHtml():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert 'id="loading-overlay"' in html
    assert 'id="benchmark-case-grid"' in html
    assert "Investigating incident" in html
    assert "Investigate Incident" in html
    assert "What failed?" in html
    assert 'id="progress-phases"' not in html


def testLoaderPhaseCopyMatchesSpec():
    titles = [title for _, title in LOADER_PHASE_COPY]
    assert titles[0] == "Reading incident logs and reconstructing the workflow"
    assert len(LOADER_PHASE_COPY) == 5


def testStoryPhasesUseHumanTitlesNotRawEvents():
    phases = [
        PipelinePhase(
            phase_id="diagnosis",
            title="Diagnosis",
            status="complete",
            details=[
                TraceStepDetail(
                    label="baseline.llm_response",
                    status="complete",
                    summary="Baseline diagnosis: divergence at 'usage_aggregate'.",
                    agent="baseline",
                    event="llm_response",
                    evidence_log_ids=["c14-02"],
                ),
                TraceStepDetail(
                    label="rule_checker.hypothesis_selected",
                    status="complete",
                    summary="Challenger hypothesis selected: divergence at 'billing_run'.",
                    agent="rule_checker",
                    event="hypothesis_selected",
                ),
            ],
        ),
        PipelinePhase(
            phase_id="safety_gates",
            title="Safety Gates",
            status="complete",
            details=[
                TraceStepDetail(
                    label="verifier.adjudication_complete",
                    status="complete",
                    summary="Adjudication decision: keep_baseline (confidence 0.9).",
                    agent="verifier",
                    event="adjudication_complete",
                    decision="keep_baseline",
                ),
            ],
        ),
    ]
    storyPhases = buildStoryPhases(phases)
    titles = [phase.title for phase in storyPhases]
    assert titles == ["Analyze", "Diagnose", "Validate", "Evidence Retrieval", "Report"]
    diagnose = next(phase for phase in storyPhases if phase.phase_id == "diagnose")
    assert "baseline.llm_response" not in diagnose.description
    validate = next(phase for phase in storyPhases if phase.phase_id == "validate")
    assert validate.gate_decision == "keep baseline"


def testFailureTitleFromDivergenceStep(case01Diagnosis):
    assert buildFailureTitle(case01Diagnosis) == "Inventory reserve failed"


def testDiagnosisHeroUsesFailureTitleNotCulpritMessage(case01, case01Diagnosis):
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    story = buildIncidentStory(metadata, case01Diagnosis, hydrated, [], buildCausalChain(case01, case01Diagnosis), True)

    assert story.failure_title == "Inventory reserve failed"
    assert story.divergence_step == "inventory_reserve"
    assert story.root_cause_description == describeCategory("sequence_skip")
    assert story.confidence_label in ("High confidence", "Adjudicated diagnosis")
    assert all(logId in case01Diagnosis.evidence_log_ids + case01Diagnosis.culprit_log_ids
               for logId in story.key_evidence_log_ids)


def testCase11MechanismChainOrder():
    case = loadCaseFromBenchmark("case_11")
    diagnosis = InvestigationResult(
        divergence_step="seat_allocate",
        root_cause_category=RootCauseCategory.CONFIG_DRIFT,
        culprit_log_ids=["c11-04", "c11-05"],
        evidence_log_ids=["c11-03", "c11-04", "c11-05", "c11-06", "c11-07"],
        explanation="Billing profile pending caused tenant inactive flag; seat allocation skipped.",
    )
    hydrated = buildHydratedLogEntries(case, diagnosis)
    chain = buildEvidenceMechanismChain(diagnosis, hydrated)
    labels = [node.label for node in chain]
    assert labels[0] == "Billing profile pending"
    assert any("Seat allocation skipped" in label for label in labels)
    assert labels.index("Billing profile pending") < labels.index("Seat allocation skipped: tenant flag inactive")


def testMechanismChainMarksCulpritsAsFailure(case01, case01Diagnosis):
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    chain = buildEvidenceMechanismChain(case01Diagnosis, hydrated)
    failureNodes = [node for node in chain if node.kind == "failure"]
    assert failureNodes
    assert all(node.log_id in case01Diagnosis.culprit_log_ids for node in failureNodes)


def testProcessFlowMarksFailedStep(case14, case14Diagnosis):
    metadata = buildCaseMetadata(case14)
    hydrated = buildHydratedLogEntries(case14, case14Diagnosis)
    causal = buildCausalChain(case14, case14Diagnosis)
    story = buildIncidentStory(metadata, case14Diagnosis, hydrated, [], causal, True)

    failedSteps = [step for step in story.process_steps if step.state == "failed"]
    assert len(failedSteps) == 1
    assert failedSteps[0].step == "usage_aggregate"
    assert failedSteps[0].culprit_log_ids == case14Diagnosis.culprit_log_ids


def testDiagnosisFieldsUnchangedInStory(case14, case14Diagnosis):
    metadata = buildCaseMetadata(case14)
    hydrated = buildHydratedLogEntries(case14, case14Diagnosis)
    causal = buildCausalChain(case14, case14Diagnosis)
    story = buildIncidentStory(metadata, case14Diagnosis, hydrated, [], causal, True)

    assert story.divergence_step == case14Diagnosis.divergence_step
    assert story.root_cause_category == case14Diagnosis.root_cause_category.value
    assert story.culprit_log_ids == case14Diagnosis.culprit_log_ids


def testWhyItFailedGroundedInDiagnosis(case01, case01Diagnosis):
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    rendered = buildWhyItFailed(case01Diagnosis, metadata, hydrated)
    assert "inventory_reserve" in rendered.lower() or "skipped" in rendered.lower()
    assert "likely" not in rendered.lower()


def testWhyItFailedDoesNotInventImpact(case01Diagnosis):
    metadata = buildCaseMetadata(next(item for item in buildCases() if item.case_id == "case_01"))
    diagnosis = case01Diagnosis.model_copy(update={"explanation": "Reservation skipped at inventory_reserve."})
    rendered = buildWhyItFailed(diagnosis, metadata, [])
    assert "lost sale" not in rendered.lower()
    assert "revenue" not in rendered.lower()


def testIncidentSummaryUsesNewHierarchy(case01, case01Diagnosis):
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, case01Diagnosis)
    story = buildIncidentStory(metadata, case01Diagnosis, hydrated, [], buildCausalChain(case01, case01Diagnosis), True)
    assert "ROOT CAUSE DETECTED" not in story.incident_summary
    assert story.failure_title in story.incident_summary
    assert "Divergence: inventory_reserve" in story.incident_summary
    assert "Why:" in story.incident_summary


def testAiTraceCollapsedByDefaultInHtml():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert 'details class="result-section trace-panel"' in html
    assert "Show investigation process" in html
    assert "Investigation Trace" not in html
    assert "baseline.llm_response" not in html


def testHeroAndToolbarPresentInHtml():
    htmlPath = Path(__file__).resolve().parent.parent / "ui" / "static" / "investigate.html"
    html = htmlPath.read_text(encoding="utf-8")
    assert 'id="hero-failure-title"' in html
    assert 'id="hero-divergence"' in html
    assert 'id="hero-root-cause"' in html
    assert 'id="mechanism-chain"' in html
    assert 'id="view-postmortem-btn"' in html
    assert 'id="copy-summary-btn"' in html
    assert "Root Cause Detected" not in html


def testKeyEvidenceLimitedToThree(case01, case01Diagnosis):
    diagnosis = case01Diagnosis.model_copy(update={"evidence_log_ids": ["c01-02", "c01-03", "c01-04", "c01-05"]})
    metadata = buildCaseMetadata(case01)
    hydrated = buildHydratedLogEntries(case01, diagnosis)
    story = buildIncidentStory(metadata, diagnosis, hydrated, [], buildCausalChain(case01, diagnosis), True)
    assert len(story.key_evidence_log_ids) <= 3


def testStoryPhasesPendingWhenNoTrajectory():
    metadata = buildCaseMetadata(next(item for item in buildCases() if item.case_id == "case_01"))
    diagnosis = InvestigationResult(
        divergence_step="inventory_reserve",
        root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
        culprit_log_ids=["c01-02"],
        evidence_log_ids=["c01-02"],
        explanation="Skipped.",
    )
    hydrated = buildHydratedLogEntries(next(item for item in buildCases() if item.case_id == "case_01"), diagnosis)
    story = buildIncidentStory(metadata, diagnosis, hydrated, [], buildCausalChain(
        next(item for item in buildCases() if item.case_id == "case_01"), diagnosis
    ), True)
    pending = [phase for phase in story.story_phases if phase.status == "pending"]
    assert len(pending) == 5
