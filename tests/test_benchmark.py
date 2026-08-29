"""Benchmark integrity tests for generated evaluation cases (Phase 1.1)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from generate_data import buildCases, writeCases
from shared.case_loader import CASES_DIR, assertLlmPayloadIsClean, loadAllCases, serializeForLlm, stripForLlm
from shared.schemas import EvalCase, InvestigationResult, RootCauseCategory
from shared.scoring import scoreInvestigation

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", autouse=True)
def generateBenchmarkCases():
    writeCases(CASES_DIR)


def testFifteenCaseFilesExist():
    cases = loadAllCases()
    assert len(cases) == 15
    assert [case.case_id for case in cases] == [f"case_{index:02d}" for index in range(1, 16)]


def testAllCasesValidateAgainstSchema():
    for case in loadAllCases():
        assert isinstance(case, EvalCase)


def testDivergenceStepInExpectedSequence():
    for case in loadAllCases():
        assert case.ground_truth.divergence_step in case.process_context.expected_sequence


def testEvidenceAndCulpritIdsExistInRawLogs():
    for case in loadAllCases():
        logIds = {log.log_id for log in case.raw_logs}
        for evidenceId in case.ground_truth.required_evidence_ids:
            assert evidenceId in logIds, f"{case.case_id} missing required evidence {evidenceId}"
        for culpritId in case.ground_truth.culprit_log_ids:
            assert culpritId in logIds, f"{case.case_id} missing culprit {culpritId}"


def testAtLeastSixDecoyDiagnosisCases():
    decoyCases = [case for case in loadAllCases() if case.ground_truth.decoy_diagnosis]
    assert len(decoyCases) >= 6


def testDecoyDiagnosisIntegrity():
    for case in loadAllCases():
        decoy = case.ground_truth.decoy_diagnosis
        if decoy is None:
            continue
        logIds = {log.log_id for log in case.raw_logs}
        for decoyId in decoy.decoy_evidence_ids:
            assert decoyId in logIds
        for culpritId in decoy.culprit_log_ids:
            assert culpritId in logIds
        assert decoy.root_cause_category != case.ground_truth.root_cause_category or (
            decoy.divergence_step != case.ground_truth.divergence_step
        )
        assert decoy.decoy_type


def testAtLeastSixDistinctDecoyTypes():
    decoyTypes = {
        case.ground_truth.decoy_diagnosis.decoy_type
        for case in loadAllCases()
        if case.ground_truth.decoy_diagnosis
    }
    assert len(decoyTypes) >= 6


def testAtLeastSixHardCasesWithSufficientLogs():
    hardCases = [case for case in loadAllCases() if case.meta.difficulty == "hard"]
    assert len(hardCases) >= 6
    for case in hardCases:
        assert 15 <= len(case.raw_logs) <= 30, f"{case.case_id} has {len(case.raw_logs)} logs"


def testStandardCasesHaveModerateLogCount():
    standardCases = [case for case in loadAllCases() if case.meta.difficulty == "standard"]
    assert len(standardCases) >= 5
    for case in standardCases:
        assert 10 <= len(case.raw_logs) <= 16, f"{case.case_id} has {len(case.raw_logs)} logs"


def testCaseFifteenIsHardSilentDivergence():
    case = next(case for case in loadAllCases() if case.case_id == "case_15")
    assert case.meta.difficulty == "hard"
    assert case.meta.failure_pattern == "silent_divergence"
    assert case.ground_truth.root_cause_category == RootCauseCategory.ENTITLEMENT_MISMATCH
    assert case.ground_truth.decoy_diagnosis is not None


def testDomainSplit():
    cases = loadAllCases()
    domains = Counter(case.meta.domain for case in cases)
    assert domains["ecommerce"] == 5
    assert domains["fintech"] == 5
    assert domains["b2b_saas"] == 5


def testDifficultyFactorsPresentOnAllCases():
    for case in loadAllCases():
        factors = case.meta.difficulty_factors
        assert 0 <= factors.composite_score <= 18
        assert factors.log_noise >= 0


def testMetaStrippedForLlm():
    for case in loadAllCases():
        llmCase = stripForLlm(case)
        payload = serializeForLlm(case)
        assertLlmPayloadIsClean(payload)
        assert not hasattr(llmCase, "meta")
        dumped = json.loads(payload)
        assert set(dumped.keys()) == {"case_id", "process_context", "raw_logs"}


def testDifficultyMetadataCannotAffectScoring():
    case = loadAllCases()[0]
    originalScore = scoreInvestigation(
        InvestigationResult(
            divergence_step=case.ground_truth.divergence_step,
            root_cause_category=case.ground_truth.root_cause_category,
            culprit_log_ids=case.ground_truth.culprit_log_ids,
            evidence_log_ids=case.ground_truth.required_evidence_ids,
            explanation="test",
        ),
        case.ground_truth,
        {log.log_id for log in case.raw_logs},
    )
    mutatedMeta = case.meta.model_copy(
        update={
            "difficulty": "hard",
            "baseline_hypothesis": "agent",
            "difficulty_factors": case.meta.difficulty_factors.model_copy(
                update={
                    "log_noise": 3,
                    "causal_distance": 3,
                    "competing_hypotheses": 3,
                    "evidence_dispersion": 3,
                    "metadata_conflict": 3,
                    "temporal_ambiguity": 3,
                }
            ),
        }
    )
    assert mutatedMeta.difficulty != case.meta.difficulty or (
        mutatedMeta.difficulty_factors.composite_score != case.meta.difficulty_factors.composite_score
    )
    repeatScore = scoreInvestigation(
        InvestigationResult(
            divergence_step=case.ground_truth.divergence_step,
            root_cause_category=case.ground_truth.root_cause_category,
            culprit_log_ids=case.ground_truth.culprit_log_ids,
            evidence_log_ids=case.ground_truth.required_evidence_ids,
            explanation="test",
        ),
        case.ground_truth,
        {log.log_id for log in case.raw_logs},
    )
    assert repeatScore.total == originalScore.total


def testBaselineHypothesisFieldNotExpectedWinner():
    for case in loadAllCases():
        assert hasattr(case.meta, "baseline_hypothesis")
        assert case.meta.baseline_hypothesis in {"baseline", "agent", "either"}


def testBuildCasesMatchesWrittenFiles():
    built = buildCases()
    loaded = loadAllCases()
    assert len(built) == len(loaded)
    for builtCase, loadedCase in zip(built, loaded):
        assert builtCase.case_id == loadedCase.case_id
        assert builtCase.ground_truth.divergence_step == loadedCase.ground_truth.divergence_step
