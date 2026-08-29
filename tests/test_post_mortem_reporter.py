"""Tests for evidence-grounded post-mortem reporter."""

from __future__ import annotations

import json

import pytest

from agents.log_lookup import LogLookupError, LogLookupTool
from agents.post_mortem_reporter import (
    REQUIRED_POST_MORTEM_SECTIONS,
    assertDiagnosisUnchanged,
    assertEvidenceGrounding,
    assertRequiredPostMortemSections,
    buildClaimTraces,
    buildEvidenceTableMarkdown,
    buildPostMortemPrompt,
    hydrateDiagnosisLogs,
    retrieveEvidenceLogs,
    runPostMortemReporter,
)
from generate_data import buildCases
from shared.llm import LlmCallResult
from shared.schemas import InvestigationResult, PostMortemReport, RootCauseCategory


def _sampleMarkdown(caseId: str, diagnosis: InvestigationResult) -> str:
    sections = "\n\n".join(
        f"## {title}\nNarrative for {title} citing {diagnosis.culprit_log_ids[0]} "
        f"and {diagnosis.evidence_log_ids[-1]}."
        for title in REQUIRED_POST_MORTEM_SECTIONS
    )
    return (
        f"# Post-Mortem: {caseId}\n\n"
        f"{sections}\n\n"
        f"Diagnosis anchor: {diagnosis.divergence_step} / "
        f"{diagnosis.root_cause_category.value} / culprits={diagnosis.culprit_log_ids}\n"
    )


class MockLlmClient:
    def __init__(self, markdown: str):
        self.markdown = markdown
        self.lastPrompt = ""

    def completeJson(self, prompt: str, modelClass: type[PostMortemReport], stage: str = "unknown") -> LlmCallResult:
        self.lastPrompt = prompt
        return LlmCallResult(
            parsed=PostMortemReport(markdown=self.markdown),
            raw_response=json.dumps({"markdown": self.markdown}),
            retry_count=0,
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
        explanation="Inventory reservation was skipped.",
    )


def testFetchLogDetailsReturnsExistingLog(case01):
    tool = LogLookupTool(case01.raw_logs)
    log = tool.fetch_log_details("c01-02")
    assert log.log_id == "c01-02"
    assert log.message == "Reservation skipped: legacy fast-path enabled"
    assert log.metadata["reservation_status"] == "skipped"


def testFetchLogDetailsRejectsUnknownId(case01):
    tool = LogLookupTool(case01.raw_logs)
    with pytest.raises(LogLookupError, match="Unknown log ID"):
        tool.fetch_log_details("c01-999")


def testFetchLogDetailsReturnsCopyNotMutableReference(case01):
    tool = LogLookupTool(case01.raw_logs)
    log = tool.fetch_log_details("c01-02")
    log.message = "mutated"
    original = tool.fetch_log_details("c01-02")
    assert original.message == "Reservation skipped: legacy fast-path enabled"


def testRetrieveEvidenceLogsSeparatesUnknown(case01, case01Diagnosis):
    tool = LogLookupTool(case01.raw_logs)
    retrieved, unknown = retrieveEvidenceLogs(
        tool,
        case01Diagnosis.evidence_log_ids + ["c01-999"],
    )
    assert set(retrieved.keys()) == {"c01-02", "c01-03"}
    assert unknown == ["c01-999"]


def testReporterPreservesImmutableDiagnosis(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    artifact = runPostMortemReporter(case01, case01Diagnosis, client)
    assert artifact.diagnosis.divergence_step == case01Diagnosis.divergence_step
    assert artifact.diagnosis.root_cause_category == case01Diagnosis.root_cause_category
    assert artifact.diagnosis.culprit_log_ids == case01Diagnosis.culprit_log_ids
    assertDiagnosisUnchanged(case01Diagnosis, artifact.diagnosis)


def testReporterDoesNotReturnInvestigationResultMutation(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    artifact = runPostMortemReporter(case01, case01Diagnosis, client)
    assert isinstance(artifact.diagnosis, InvestigationResult)
    assert artifact.markdown
    assert "InvestigationResult" not in artifact.markdown


def testReporterRetrievesOnlyExistingEvidence(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    artifact = runPostMortemReporter(case01, case01Diagnosis, client)
    validIds = {log.log_id for log in case01.raw_logs}
    assert set(artifact.retrieved_evidence_log_ids).issubset(validIds)
    assert artifact.retrieved_evidence_log_ids == ["c01-02", "c01-03"]


def testReporterPromptIncludesFetchedLogs(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    runPostMortemReporter(case01, case01Diagnosis, client)
    assert "fetch_log_details('c01-02')" in client.lastPrompt
    assert "fetch_log_details('c01-03')" in client.lastPrompt
    assert "IMMUTABLE DIAGNOSIS" in client.lastPrompt


def testReportContainsRequiredSections(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    artifact = runPostMortemReporter(case01, case01Diagnosis, client)
    assertRequiredPostMortemSections(artifact.markdown)
    for section in REQUIRED_POST_MORTEM_SECTIONS:
        assert section in artifact.markdown


def testReportIncludesEvidenceTableAndTrace(case01, case01Diagnosis):
    client = MockLlmClient(_sampleMarkdown(case01.case_id, case01Diagnosis))
    artifact = runPostMortemReporter(case01, case01Diagnosis, client)
    assert "## Evidence" in artifact.markdown
    assert "## Evidence Trace" in artifact.markdown
    assert "| c01-02 |" in artifact.markdown
    assert artifact.claim_traces
    assert artifact.evidence_table_markdown


def testBuildEvidenceTableMarkdown(case01, case01Diagnosis):
    evidenceLogs, _, _ = hydrateDiagnosisLogs(case01, case01Diagnosis)
    table = buildEvidenceTableMarkdown(case01Diagnosis, evidenceLogs)
    assert "c01-02" in table
    assert "culprit" in table


def testBuildClaimTracesLinksLogsToClaims(case01, case01Diagnosis):
    evidenceLogs, culpritLogs, _ = hydrateDiagnosisLogs(case01, case01Diagnosis)
    hydrated = dict(evidenceLogs)
    hydrated.update(culpritLogs)
    traces = buildClaimTraces(case01Diagnosis, hydrated)
    assert any("inventory_reserve" in trace.claim for trace in traces)
    assert any("c01-02" in trace.supporting_log_ids for trace in traces)


def testAssertEvidenceGroundingRejectsFabricatedLog(case01Diagnosis):
    markdown = "## Executive Summary\nFabricated log c01-99 appears here."
    with pytest.raises(ValueError, match="not hydrated"):
        assertEvidenceGrounding(markdown, {"c01-02", "c01-03"})


def testReporterRejectsUngroundedLlmOutput(case01, case01Diagnosis):
    badMarkdown = "\n\n".join(
        f"## {title}\nMentions phantom log c01-99."
        for title in REQUIRED_POST_MORTEM_SECTIONS
    )
    client = MockLlmClient(badMarkdown)
    with pytest.raises(ValueError, match="not hydrated"):
        runPostMortemReporter(case01, case01Diagnosis, client)


def testBuildPostMortemPromptListsUnknownEvidence(case01, case01Diagnosis):
    tool = LogLookupTool(case01.raw_logs)
    evidenceLogs, unknown = retrieveEvidenceLogs(tool, ["c01-02", "missing-id"])
    culpritLogs, _ = retrieveEvidenceLogs(tool, case01Diagnosis.culprit_log_ids)
    prompt = buildPostMortemPrompt(case01, case01Diagnosis, evidenceLogs, culpritLogs, unknown)
    assert "missing-id" in prompt
    assert "UNKNOWN LOG IDS" in prompt


def testAssertDiagnosisUnchangedRejectsCulpritEdit(case01Diagnosis):
    mutated = case01Diagnosis.model_copy(update={"culprit_log_ids": ["c01-03"]})
    with pytest.raises(ValueError, match="culprit_log_ids"):
        assertDiagnosisUnchanged(case01Diagnosis, mutated)


def testAssertDiagnosisUnchangedRejectsStepEdit(case01Diagnosis):
    mutated = case01Diagnosis.model_copy(update={"divergence_step": "payment_authorize"})
    with pytest.raises(ValueError, match="divergence_step"):
        assertDiagnosisUnchanged(case01Diagnosis, mutated)


def testReporterHandlesUnknownBaselineEvidenceIds(case01, case01Diagnosis):
    diagnosis = case01Diagnosis.model_copy(update={"evidence_log_ids": ["c01-02", "c01-ghost"]})
    markdown = _sampleMarkdown(case01.case_id, diagnosis).replace("c01-03", "c01-02")
    client = MockLlmClient(markdown)
    artifact = runPostMortemReporter(case01, diagnosis, client)
    assert artifact.unknown_log_ids == ["c01-ghost"]
    assert "c01-ghost" in client.lastPrompt
