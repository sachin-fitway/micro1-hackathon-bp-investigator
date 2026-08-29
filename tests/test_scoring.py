"""Unit tests for the weighted scoring rubric."""

from __future__ import annotations

import pytest

from shared.schemas import GroundTruth, InvestigationResult, RootCauseCategory
from shared.scoring import (
    WEIGHT_EVIDENCE_PRECISION,
    WEIGHT_EVIDENCE_RECALL,
    WEIGHT_FAILURE_POINT,
    WEIGHT_NO_FABRICATED,
    WEIGHT_ROOT_CAUSE,
    scoreEvidencePrecision,
    scoreEvidenceRecall,
    scoreFailurePoint,
    scoreInvestigation,
    scoreNoFabricated,
    scoreRootCause,
)


def _groundTruth(**overrides) -> GroundTruth:
    defaults = {
        "divergence_step": "inventory_reserve",
        "root_cause_category": RootCauseCategory.SEQUENCE_SKIP,
        "culprit_log_ids": ["log-a"],
        "required_evidence_ids": ["log-a", "log-b"],
    }
    defaults.update(overrides)
    return GroundTruth(**defaults)


def _result(**overrides) -> InvestigationResult:
    defaults = {
        "divergence_step": "inventory_reserve",
        "root_cause_category": RootCauseCategory.SEQUENCE_SKIP,
        "culprit_log_ids": ["log-a"],
        "evidence_log_ids": ["log-a", "log-b"],
        "explanation": "Reservation skipped before payment.",
    }
    defaults.update(overrides)
    return InvestigationResult(**defaults)


def testPerfectScoreOnExactMatch():
    groundTruth = _groundTruth()
    predicted = _result()
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a", "log-b", "log-c"})
    assert breakdown.total == pytest.approx(1.0)
    assert breakdown.failure_point == 1.0
    assert breakdown.root_cause == 1.0
    assert breakdown.evidence_recall == 1.0
    assert breakdown.evidence_precision == 1.0
    assert breakdown.no_fabricated == 1.0


def testZeroRootCauseWhenCategoryWrongButStepRight():
    groundTruth = _groundTruth()
    predicted = _result(root_cause_category=RootCauseCategory.TIMEOUT_STALL)
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a", "log-b"})
    assert breakdown.failure_point == 1.0
    assert breakdown.root_cause == 0.0
    assert breakdown.total == pytest.approx(1.0 - WEIGHT_ROOT_CAUSE)


def testPartialRootCauseWhenSemanticallyEquivalent():
    groundTruth = _groundTruth()
    predicted = _result(root_cause_category=RootCauseCategory.FALSE_SUCCESS_SIGNAL)
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a", "log-b"})
    assert breakdown.failure_point == 1.0
    assert breakdown.root_cause == pytest.approx(0.5)
    assert breakdown.total == pytest.approx(1.0 - WEIGHT_ROOT_CAUSE * 0.5)


def testEvidenceRecallHalfWhenHalfRequiredCited():
    groundTruth = _groundTruth(required_evidence_ids=["log-a", "log-b", "log-c", "log-d"])
    predicted = _result(evidence_log_ids=["log-a", "log-b"])
    assert scoreEvidenceRecall(predicted, groundTruth) == pytest.approx(0.5)


def testPrecisionTrapManyIrrelevantLogs():
    groundTruth = _groundTruth(required_evidence_ids=["log-a", "log-b"])
    irrelevant = [f"irrelevant-{index}" for index in range(10)]
    predicted = _result(evidence_log_ids=["log-a", "log-b", *irrelevant])
    recall = scoreEvidenceRecall(predicted, groundTruth)
    precision = scoreEvidencePrecision(predicted, groundTruth)
    assert recall == pytest.approx(1.0)
    assert precision == pytest.approx(2 / 12)
    validIds = set(irrelevant) | {"log-a", "log-b"}
    breakdown = scoreInvestigation(predicted, groundTruth, validIds)
    expectedTotal = (
        WEIGHT_FAILURE_POINT
        + WEIGHT_ROOT_CAUSE
        + WEIGHT_EVIDENCE_RECALL
        + WEIGHT_EVIDENCE_PRECISION * (2 / 12)
        + WEIGHT_NO_FABRICATED
    )
    assert breakdown.total == pytest.approx(expectedTotal)


def testFabricatedIdZeroesNoFabricatedDimension():
    groundTruth = _groundTruth()
    predicted = _result(evidence_log_ids=["log-a", "log-b", "fake-log"])
    assert scoreNoFabricated(predicted, {"log-a", "log-b"}) == 0.0
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a", "log-b"})
    assert breakdown.no_fabricated == 0.0
    assert breakdown.evidence_precision == pytest.approx(2 / 3)
    expectedTotal = (
        WEIGHT_FAILURE_POINT
        + WEIGHT_ROOT_CAUSE
        + WEIGHT_EVIDENCE_RECALL
        + WEIGHT_EVIDENCE_PRECISION * (2 / 3)
    )
    assert breakdown.total == pytest.approx(expectedTotal)


def testEmptyEvidenceBothEmptyScoresOne():
    groundTruth = _groundTruth(required_evidence_ids=[])
    predicted = _result(evidence_log_ids=[])
    assert scoreEvidenceRecall(predicted, groundTruth) == 1.0
    assert scoreEvidencePrecision(predicted, groundTruth) == 1.0


def testEmptyEvidenceWithRequiredScoresZeroPrecision():
    groundTruth = _groundTruth(required_evidence_ids=["log-a"])
    predicted = _result(evidence_log_ids=[])
    assert scoreEvidenceRecall(predicted, groundTruth) == 0.0
    assert scoreEvidencePrecision(predicted, groundTruth) == 0.0


def testFailurePointCaseInsensitive():
    groundTruth = _groundTruth(divergence_step="Inventory_Reserve")
    predicted = _result(divergence_step="inventory_reserve")
    assert scoreFailurePoint(predicted, groundTruth) == 1.0


def testFabricatedCulpritIdFailsNoFabricated():
    groundTruth = _groundTruth(culprit_log_ids=["log-a"])
    predicted = _result(culprit_log_ids=["missing-log"], evidence_log_ids=["log-a", "log-b"])
    assert scoreNoFabricated(predicted, {"log-a", "log-b"}) == 0.0
