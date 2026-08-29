"""Tests for deterministic adjudication gates."""

from __future__ import annotations

from agents.adjudication_gates import (
    blocksFalseSuccessOverSequenceSkip,
    blocksSameStepSupportLogPromotion,
    evaluateOverrideBlocks,
    isDownstreamDivergence,
)
from shared.schemas import InvestigationResult, RootCauseCategory

ECOMMERCE_SEQUENCE = [
    "payment_authorize",
    "payment_capture",
    "warehouse_pick",
    "carrier_label",
    "dispatch_confirm",
]

ORDER_SEQUENCE = [
    "payment_authorize",
    "order_confirm",
    "inventory_reserve",
    "shipment_create",
]

CHECKOUT_SEQUENCE = [
    "cart_validate",
    "inventory_reserve",
    "payment_authorize",
    "order_confirm",
]


def _result(
    step: str,
    category: RootCauseCategory,
    culprits: list[str],
    evidence: list[str],
) -> InvestigationResult:
    return InvestigationResult(
        divergence_step=step,
        root_cause_category=category,
        culprit_log_ids=culprits,
        evidence_log_ids=evidence,
        explanation="test",
    )


def testCase02BlocksUpstreamFalseSuccessOverSequenceSkip():
    baseline = _result("order_confirm", RootCauseCategory.SEQUENCE_SKIP, ["log-a"], ["log-a"])
    challenger = _result(
        "payment_authorize",
        RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        ["log-b"],
        ["log-b"],
    )
    assert blocksFalseSuccessOverSequenceSkip(baseline, challenger, ORDER_SEQUENCE)


def testSameStepSupportPromotionBlocksConcurrentRelabeling():
    baseline = _result("entitlement_sync", RootCauseCategory.WEBHOOK_MISSING, ["anchor"], ["anchor", "state"])
    challenger = _result(
        "entitlement_sync",
        RootCauseCategory.CONFIG_DRIFT,
        ["state"],
        ["anchor", "state"],
    )
    timestamps = {"anchor": "2026-03-13T08:00:01Z", "state": "2026-03-13T08:00:01Z"}
    assert blocksSameStepSupportLogPromotion(
        baseline,
        challenger,
        ["contract_signed", "entitlement_sync", "tenant_provision"],
        timestamps,
    )


def testSameStepSupportPromotionAllowsDownstreamEffectCulprit():
    baseline = _result(
        "inventory_reserve",
        RootCauseCategory.CONFIG_DRIFT,
        ["skip-log"],
        ["skip-log", "effect-log"],
    )
    challenger = _result(
        "inventory_reserve",
        RootCauseCategory.SEQUENCE_SKIP,
        ["effect-log"],
        ["skip-log", "effect-log"],
    )
    timestamps = {
        "skip-log": "2026-03-12T10:00:03Z",
        "effect-log": "2026-03-12T10:00:05Z",
    }
    assert not blocksSameStepSupportLogPromotion(
        baseline,
        challenger,
        CHECKOUT_SEQUENCE,
        timestamps,
    )


def testSameStepSupportPromotionAllowsNewUpstreamAnchor():
    baseline = _result("seat_allocate", RootCauseCategory.CONFIG_DRIFT, ["sym-a", "sym-b"], ["sym-a", "sym-b"])
    challenger = _result(
        "seat_allocate",
        RootCauseCategory.CONFIG_DRIFT,
        ["new-anchor", "sym-b"],
        ["new-anchor", "sym-a", "sym-b"],
    )
    timestamps = {
        "sym-a": "2026-03-12T10:00:03Z",
        "sym-b": "2026-03-12T10:00:04Z",
        "new-anchor": "2026-03-12T10:00:02Z",
    }
    assert not blocksSameStepSupportLogPromotion(
        baseline,
        challenger,
        ["billing_sync", "seat_allocate", "welcome_email"],
        timestamps,
    )


def testEvaluateOverrideBlocksIncludesSameStepRoleGate():
    baseline = _result("entitlement_sync", RootCauseCategory.WEBHOOK_MISSING, ["anchor"], ["anchor", "state"])
    challenger = _result(
        "entitlement_sync",
        RootCauseCategory.CONFIG_DRIFT,
        ["state"],
        ["anchor", "state"],
    )
    blocks = evaluateOverrideBlocks(
        baseline,
        challenger,
        ["contract_signed", "entitlement_sync", "tenant_provision"],
        [],
        [],
        "Log state shows mismatch.",
        {"anchor", "state"},
        {"anchor": "2026-03-13T08:00:01Z", "state": "2026-03-13T08:00:01Z"},
    )
    assert any("SAME_STEP_CAUSAL_ROLE" in block for block in blocks)


def testCase09BlocksDownstreamChallenger():
    baseline = _result("fraud_score", RootCauseCategory.DUPLICATE_PROCESSING, ["up"], ["up"])
    challenger = _result("issuer_approve", RootCauseCategory.DUPLICATE_PROCESSING, ["down"], ["down"])
    assert isDownstreamDivergence(
        challenger.divergence_step,
        baseline.divergence_step,
        ["payment_init", "fraud_score", "issuer_approve", "payment_execute"],
    )
