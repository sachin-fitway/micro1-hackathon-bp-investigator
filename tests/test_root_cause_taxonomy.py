"""Tests for root-cause taxonomy and tolerant scoring."""

from __future__ import annotations

import pytest

from shared.root_cause_taxonomy import (
    ROOT_CAUSE_EQUIVALENCE_GROUPS,
    ROOT_CAUSE_PARTIAL_CREDIT,
    areEquivalentCategories,
    buildEquivalenceLookup,
    scoreRootCauseMatch,
)
from shared.schemas import GroundTruth, RootCauseCategory
from shared.scoring import WEIGHT_ROOT_CAUSE, scoreInvestigation
from tests.test_scoring import _groundTruth, _result


def testEquivalenceGroupsAreDocumented():
    assert len(ROOT_CAUSE_EQUIVALENCE_GROUPS) >= 5
    lookup = buildEquivalenceLookup()
    for group in ROOT_CAUSE_EQUIVALENCE_GROUPS:
        for category in group:
            assert category in lookup
            assert group.issubset(lookup[category])


def testNoTransitiveEquivalenceAcrossGroups():
    assert not areEquivalentCategories(
        RootCauseCategory.SEQUENCE_SKIP,
        RootCauseCategory.CONFIG_DRIFT,
    )


def testSequenceSkipEquivalentToFalseSuccessSignal():
    assert areEquivalentCategories(
        RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        RootCauseCategory.SEQUENCE_SKIP,
    )
    assert scoreRootCauseMatch(
        RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        _groundTruth(root_cause_category=RootCauseCategory.SEQUENCE_SKIP),
    ) == pytest.approx(ROOT_CAUSE_PARTIAL_CREDIT)


def testRaceConditionEquivalentToDuplicateProcessing():
    groundTruth = _groundTruth(root_cause_category=RootCauseCategory.RACE_CONDITION)
    assert scoreRootCauseMatch(RootCauseCategory.DUPLICATE_PROCESSING, groundTruth) == pytest.approx(
        ROOT_CAUSE_PARTIAL_CREDIT
    )


def testEntitlementMismatchEquivalentToWebhookMissing():
    groundTruth = _groundTruth(root_cause_category=RootCauseCategory.ENTITLEMENT_MISMATCH)
    assert scoreRootCauseMatch(RootCauseCategory.WEBHOOK_MISSING, groundTruth) == pytest.approx(
        ROOT_CAUSE_PARTIAL_CREDIT
    )


def testConfigDriftEquivalentToFalseSuccessSignal():
    groundTruth = _groundTruth(root_cause_category=RootCauseCategory.CONFIG_DRIFT)
    assert scoreRootCauseMatch(RootCauseCategory.FALSE_SUCCESS_SIGNAL, groundTruth) == pytest.approx(
        ROOT_CAUSE_PARTIAL_CREDIT
    )


def testUnrelatedCategoriesScoreZero():
    groundTruth = _groundTruth(root_cause_category=RootCauseCategory.SEQUENCE_SKIP)
    assert scoreRootCauseMatch(RootCauseCategory.TIMEOUT_STALL, groundTruth) == 0.0


def testAcceptableRootCausesScoreFullCredit():
    groundTruth = _groundTruth(
        root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
        acceptable_root_causes=[RootCauseCategory.TIMEOUT_STALL],
    )
    assert scoreRootCauseMatch(RootCauseCategory.TIMEOUT_STALL, groundTruth) == 1.0


def testPartialRootCauseUpdatesInvestigationTotal():
    groundTruth = _groundTruth(root_cause_category=RootCauseCategory.SEQUENCE_SKIP)
    predicted = _result(root_cause_category=RootCauseCategory.FALSE_SUCCESS_SIGNAL)
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a", "log-b"})
    assert breakdown.root_cause == pytest.approx(ROOT_CAUSE_PARTIAL_CREDIT)
    assert breakdown.total == pytest.approx(1.0 - WEIGHT_ROOT_CAUSE * (1.0 - ROOT_CAUSE_PARTIAL_CREDIT))


def testDecoyCategoryAtWrongStepStillFailsOverall():
    """Category partial credit does not rescue wrong divergence_step."""
    groundTruth = _groundTruth(
        divergence_step="fraud_score",
        root_cause_category=RootCauseCategory.RACE_CONDITION,
        required_evidence_ids=["log-a"],
        culprit_log_ids=["log-a"],
    )
    predicted = _result(
        divergence_step="issuer_approve",
        root_cause_category=RootCauseCategory.DUPLICATE_PROCESSING,
        evidence_log_ids=["log-a"],
        culprit_log_ids=["log-a"],
    )
    breakdown = scoreInvestigation(predicted, groundTruth, {"log-a"})
    assert breakdown.failure_point == 0.0
    assert breakdown.root_cause == pytest.approx(ROOT_CAUSE_PARTIAL_CREDIT)
    assert breakdown.total <= 0.5
