#!/usr/bin/env python3
"""Generate 15 synthetic adversarial benchmark cases (Phase 1.1 hardened)."""

from __future__ import annotations

import json
from pathlib import Path

from shared.schemas import (
    CaseMeta,
    DecoyDiagnosis,
    DifficultyFactors,
    EvalCase,
    GroundTruth,
    LogEntry,
    ProcessContext,
    RootCauseCategory,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "cases"

NOISE_SERVICES = [
    ("metrics-service", "Metric batch flushed"),
    ("cache-service", "Cache partition warmed"),
    ("cdn-service", "Edge POP health check ok"),
    ("feature-flag-service", "Flag evaluation cached"),
    ("session-service", "Session TTL refreshed"),
    ("rate-limiter", "Token bucket replenished"),
    ("config-service", "Config snapshot loaded"),
    ("tracing-service", "Trace span exported"),
]


def log(
    logId: str,
    timestamp: str,
    service: str,
    message: str,
    metadata: dict | None = None,
) -> LogEntry:
    return LogEntry(
        log_id=logId,
        timestamp=timestamp,
        service=service,
        message=message,
        metadata=metadata or {},
    )


def noiseLogs(
    prefix: str,
    correlationId: str,
    hour: int,
    minute: int,
    count: int,
    startIndex: int = 1,
) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for index in range(count):
        service, message = NOISE_SERVICES[index % len(NOISE_SERVICES)]
        second = (minute * 60 + index * 3) % 60
        adjustedMinute = minute + (minute * 60 + index * 3) // 60
        timestamp = f"2026-03-12T{hour:02d}:{adjustedMinute:02d}:{second:02d}Z"
        entries.append(
            log(
                f"{prefix}-n{startIndex + index:02d}",
                timestamp,
                service,
                message,
                {"correlation_id": correlationId, "irrelevant": True},
            )
        )
    return entries


def factors(**scores: int) -> DifficultyFactors:
    return DifficultyFactors(**scores)


def buildCases() -> list[EvalCase]:
    return [
        _case01(),
        _case02(),
        _case03(),
        _case04(),
        _case05(),
        _case06(),
        _case07(),
        _case08(),
        _case09(),
        _case10(),
        _case11(),
        _case12(),
        _case13(),
        _case14(),
        _case15(),
    ]


def _case01() -> EvalCase:
    cid = "ord-8812"
    core = [
        log("c01-01", "2026-03-12T10:00:01Z", "cart-service", "Cart validated", {"correlation_id": cid}),
        log("c01-02", "2026-03-12T10:00:03Z", "inventory-service", "Reservation skipped: legacy fast-path enabled", {"correlation_id": cid, "reservation_status": "skipped"}),
        log("c01-03", "2026-03-12T10:00:05Z", "payment-gateway", "Authorization failed: no active reservation", {"correlation_id": cid}),
        log("c01-04", "2026-03-12T10:00:06Z", "cart-service", "Checkout aborted", {"correlation_id": cid}),
        log("c01-05", "2026-03-12T10:00:02Z", "audit-service", "Checkout session opened", {"correlation_id": cid}),
        log("c01-07", "2026-03-12T10:00:07Z", "support-bot", "Customer reported cart timeout", {"correlation_id": cid}),
        log("c01-08", "2026-03-12T10:00:01Z", "edge-gateway", "Request accepted", {"correlation_id": cid}),
        log("c01-09", "2026-03-12T10:00:05Z", "fraud-service", "Risk check passed", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_01",
        process_context=ProcessContext(
            process_name="ecommerce_checkout",
            expected_sequence=["cart_validate", "inventory_reserve", "payment_authorize", "order_confirm"],
        ),
        raw_logs=core + noiseLogs("c01", cid, 10, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="inventory_reserve",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c01-02"],
            required_evidence_ids=["c01-02", "c01-03"],
        ),
        meta=CaseMeta(
            failure_pattern="sequence_skip",
            difficulty="standard",
            baseline_hypothesis="baseline",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=0, evidence_dispersion=1, metadata_conflict=0, temporal_ambiguity=0),
        ),
    )


def _case02() -> EvalCase:
    cid = "ord-9021"
    core = [
        log("c02-08", "2026-03-12T11:00:07Z", "order-service", "Order confirmation missing prior authorization", {"correlation_id": cid}),
        log("c02-03", "2026-03-12T11:00:02Z", "inventory-service", "Inventory reserved", {"correlation_id": cid}),
        log("c02-01", "2026-03-12T11:00:00Z", "cart-service", "Cart validated", {"correlation_id": cid}),
        log("c02-06", "2026-03-12T11:00:05Z", "payment-gateway", "Authorization succeeded", {"correlation_id": cid}),
        log("c02-04", "2026-03-12T11:00:03Z", "payment-gateway", "Authorization request received", {"correlation_id": cid}),
        log("c02-07", "2026-03-12T11:00:06Z", "order-service", "Confirm step invoked without auth token", {"correlation_id": cid}),
        log("c02-02", "2026-03-12T11:00:01Z", "audit-service", "Checkout started", {"correlation_id": cid}),
        log("c02-05", "2026-03-12T11:00:04Z", "fraud-service", "Risk check passed", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_02",
        process_context=ProcessContext(
            process_name="ecommerce_checkout",
            expected_sequence=["cart_validate", "inventory_reserve", "payment_authorize", "order_confirm"],
        ),
        raw_logs=core + noiseLogs("c02", cid, 11, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="order_confirm",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c02-07", "c02-08"],
            required_evidence_ids=["c02-06", "c02-07", "c02-08"],
        ),
        meta=CaseMeta(
            failure_pattern="out_of_order_delivery",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=2),
        ),
    )


def _case03() -> EvalCase:
    """Hard: clock skew + decoy pointing at payment due to timestamp order."""
    cid = "ord-7734"
    core = [
        log("c03-01", "2026-03-12T12:00:00Z", "cart-service", "Cart validated", {"correlation_id": cid}),
        log("c03-02", "2026-03-12T12:00:01Z", "coupon-service", "Coupon evaluation deferred", {"correlation_id": cid}),
        log("c03-03", "2026-03-12T11:59:58Z", "payment-gateway", "Authorization attempted with stale amount", {"correlation_id": cid, "clock_skew_ms": 2000}),
        log("c03-04", "2026-03-12T12:00:02Z", "order-service", "Order confirmation blocked", {"correlation_id": cid}),
        log("c03-05", "2026-03-12T12:00:03Z", "audit-service", "Coupon step produced no discount artifact", {"correlation_id": cid}),
        log("c03-06", "2026-03-12T12:00:04Z", "support-bot", "Customer charged wrong amount", {"correlation_id": cid}),
        log("c03-07", "2026-03-12T12:00:01Z", "pricing-service", "Price snapshot v12 applied", {"correlation_id": cid}),
        log("c03-08", "2026-03-12T12:00:02Z", "fraud-service", "Risk check passed", {"correlation_id": cid}),
        log("c03-09", "2026-03-12T12:00:03Z", "tax-service", "Tax computed on pre-discount amount", {"correlation_id": cid}),
        log("c03-10", "2026-03-12T12:00:04Z", "recommendation-service", "Cross-sell impression logged", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_03",
        process_context=ProcessContext(
            process_name="ecommerce_checkout",
            expected_sequence=["cart_validate", "coupon_apply", "payment_authorize", "order_confirm"],
        ),
        raw_logs=core + noiseLogs("c03", cid, 12, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="coupon_apply",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c03-02", "c03-05"],
            required_evidence_ids=["c03-02", "c03-05", "c03-09"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="temporal_wrong_causal_order",
                divergence_step="payment_authorize",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c03-03"],
                decoy_evidence_ids=["c03-03", "c03-06", "c03-09"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="either",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=2, causal_distance=2, competing_hypotheses=2, evidence_dispersion=2, metadata_conflict=1, temporal_ambiguity=3),
        ),
    )


def _case04() -> EvalCase:
    cid = "ord-6601"
    core = [
        log("c04-01", "2026-03-12T13:00:00Z", "cart-service", "Cart validated", {"correlation_id": cid}),
        log("c04-02", "2026-03-12T13:00:01Z", "inventory-service", "Reservation delayed: warehouse sync pending", {"correlation_id": cid}),
        log("c04-03", "2026-03-12T13:00:02Z", "coupon-service", "Coupon rejected silently: campaign expired", {"correlation_id": cid, "coupon_status": "ignored"}),
        log("c04-04", "2026-03-12T13:00:03Z", "payment-gateway", "Authorization failed: price mismatch", {"correlation_id": cid}),
        log("c04-05", "2026-03-12T13:00:04Z", "inventory-service", "Reservation completed after payment window", {"correlation_id": cid}),
        log("c04-06", "2026-03-12T13:00:05Z", "support-bot", "Checkout failed at payment", {"correlation_id": cid}),
        log("c04-07", "2026-03-12T13:00:01Z", "audit-service", "Promo code present on cart", {"correlation_id": cid}),
        log("c04-08", "2026-03-12T13:00:02Z", "fraud-service", "Risk check passed", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_04",
        process_context=ProcessContext(
            process_name="ecommerce_checkout",
            expected_sequence=["cart_validate", "inventory_reserve", "coupon_apply", "payment_authorize"],
        ),
        raw_logs=core + noiseLogs("c04", cid, 13, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="coupon_apply",
            root_cause_category=RootCauseCategory.CONFIG_DRIFT,
            culprit_log_ids=["c04-03"],
            required_evidence_ids=["c04-03", "c04-04", "c04-07"],
        ),
        meta=CaseMeta(
            failure_pattern="multiple_plausible_causes",
            difficulty="standard",
            baseline_hypothesis="baseline",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=2, evidence_dispersion=1, metadata_conflict=1, temporal_ambiguity=0),
        ),
    )


def _case05() -> EvalCase:
    """Hard: downstream carrier ERROR masks upstream payment_capture skip."""
    cid = "ord-5590"
    core = [
        log("c05-01", "2026-03-12T14:00:00Z", "payment-gateway", "Capture skipped: auth still pending", {"correlation_id": cid}),
        log("c05-02", "2026-03-12T14:00:01Z", "warehouse-service", "Pick list generated", {"correlation_id": cid}),
        log("c05-03", "2026-03-12T14:00:02Z", "carrier-service", "Label request accepted", {"correlation_id": cid}),
        log("c05-04", "2026-03-12T14:00:05Z", "carrier-service", "Dispatch timeout waiting for settlement", {"correlation_id": cid, "level": "ERROR"}),
        log("c05-05", "2026-03-12T14:00:06Z", "support-bot", "Shipment delayed", {"correlation_id": cid}),
        log("c05-06", "2026-03-12T14:00:03Z", "audit-service", "No capture receipt found", {"correlation_id": cid}),
        log("c05-07", "2026-03-12T14:00:01Z", "order-service", "Fulfillment started", {"correlation_id": cid}),
        log("c05-08", "2026-03-12T14:00:04Z", "inventory-service", "Pick confirmed", {"correlation_id": cid}),
        log("c05-09", "2026-03-12T14:00:02Z", "label-service", "Label template rendered", {"correlation_id": cid}),
        log("c05-10", "2026-03-12T14:00:03Z", "weather-service", "Route delay advisory ignored", {"correlation_id": cid}),
        log("c05-11", "2026-03-12T14:00:04Z", "partner-api", "Carrier webhook 200 received", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_05",
        process_context=ProcessContext(
            process_name="ecommerce_fulfillment",
            expected_sequence=["payment_capture", "warehouse_pick", "carrier_label", "shipment_dispatch"],
        ),
        raw_logs=core + noiseLogs("c05", cid, 14, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="payment_capture",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c05-01"],
            required_evidence_ids=["c05-01", "c05-06", "c05-04"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="downstream_error_looks_like_root",
                divergence_step="shipment_dispatch",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c05-04"],
                decoy_evidence_ids=["c05-04", "c05-05", "c05-11"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="either",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=2, causal_distance=3, competing_hypotheses=2, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=1),
        ),
    )


def _case06() -> EvalCase:
    cid = "txn-4410"
    core = [
        log("c06-01", "2026-03-12T15:00:00Z", "core-banking", "Debit initiated", {"correlation_id": cid}),
        log("c06-02", "2026-03-12T15:00:01Z", "compliance-engine", "Screening queue bypassed for trusted corridor", {"correlation_id": cid}),
        log("c06-03", "2026-03-12T15:00:02Z", "ledger-service", "Post rejected: missing compliance token", {"correlation_id": cid}),
        log("c06-04", "2026-03-12T15:00:03Z", "beneficiary-bank", "Credit never received", {"correlation_id": cid}),
        log("c06-05", "2026-03-12T15:00:04Z", "support-bot", "Transfer stuck in processing", {"correlation_id": cid}),
        log("c06-06", "2026-03-12T15:00:01Z", "audit-service", "No compliance artifact attached", {"correlation_id": cid}),
        log("c06-07", "2026-03-12T15:00:00Z", "edge-gateway", "Transfer request accepted", {"correlation_id": cid}),
        log("c06-08", "2026-03-12T15:00:02Z", "risk-service", "Velocity check passed", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_06",
        process_context=ProcessContext(
            process_name="fintech_transfer",
            expected_sequence=["account_debit", "compliance_screen", "ledger_post", "beneficiary_credit"],
        ),
        raw_logs=core + noiseLogs("c06", cid, 15, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="compliance_screen",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c06-02", "c06-06"],
            required_evidence_ids=["c06-02", "c06-06", "c06-03"],
        ),
        meta=CaseMeta(
            failure_pattern="sequence_insufficient",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="fintech",
            difficulty_factors=factors(log_noise=1, causal_distance=2, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=0),
        ),
    )


def _case07() -> EvalCase:
    cid = "txn-3322"
    core = [
        log("c07-01", "2026-03-12T16:00:00Z", "wallet-service", "Balance check passed", {"correlation_id": cid}),
        log("c07-02", "2026-03-12T16:00:01Z", "compliance-engine", "Payout released", {"correlation_id": cid, "hold_status": "active"}),
        log("c07-03", "2026-03-12T16:00:02Z", "payout-service", "Execution blocked by active hold", {"correlation_id": cid}),
        log("c07-04", "2026-03-12T16:00:03Z", "support-bot", "Merchant says payout never arrived", {"correlation_id": cid}),
        log("c07-05", "2026-03-12T16:00:01Z", "audit-service", "Hold flag still set in ledger", {"correlation_id": cid}),
        log("c07-06", "2026-03-12T16:00:02Z", "receipt-service", "Receipt not generated", {"correlation_id": cid}),
        log("c07-07", "2026-03-12T16:00:00Z", "edge-gateway", "Payout request accepted", {"correlation_id": cid}),
        log("c07-08", "2026-03-12T16:00:03Z", "risk-service", "Merchant risk score nominal", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_07",
        process_context=ProcessContext(
            process_name="fintech_payout",
            expected_sequence=["balance_check", "compliance_hold", "payout_execute", "receipt_emit"],
        ),
        raw_logs=core + noiseLogs("c07", cid, 16, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="compliance_hold",
            root_cause_category=RootCauseCategory.METADATA_MESSAGE_CONFLICT,
            culprit_log_ids=["c07-02", "c07-05"],
            required_evidence_ids=["c07-02", "c07-05", "c07-03"],
        ),
        meta=CaseMeta(
            failure_pattern="metadata_message_conflict",
            difficulty="standard",
            baseline_hypothesis="baseline",
            domain="fintech",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=1, evidence_dispersion=1, metadata_conflict=3, temporal_ambiguity=0),
        ),
    )


def _case08() -> EvalCase:
    """Hard: AML skip with custodian timeout decoy."""
    cid = "txn-2218"
    core = [
        log("c08-01", "2026-03-12T17:00:00Z", "matching-engine", "Trade matched", {"correlation_id": cid}),
        log("c08-02", "2026-03-12T16:59:57Z", "aml-service", "Screening short-circuited", {"correlation_id": cid, "clock_skew_ms": 3000}),
        log("c08-03", "2026-03-12T17:00:02Z", "settlement-service", "Batch waiting for AML clearance", {"correlation_id": cid}),
        log("c08-04", "2026-03-12T17:00:05Z", "custodian-gateway", "Transfer timeout", {"correlation_id": cid, "level": "ERROR"}),
        log("c08-05", "2026-03-12T17:00:06Z", "support-bot", "Settlement delayed overnight", {"correlation_id": cid}),
        log("c08-06", "2026-03-12T17:00:01Z", "audit-service", "No AML clearance token issued", {"correlation_id": cid, "level": "DEBUG"}),
        log("c08-07", "2026-03-12T17:00:03Z", "fx-service", "FX rate locked", {"correlation_id": cid}),
        log("c08-08", "2026-03-12T17:00:04Z", "counterparty-service", "Limit headroom ok", {"correlation_id": cid}),
        log("c08-09", "2026-03-12T17:00:02Z", "risk-service", "Counterparty limit ok", {"correlation_id": cid}),
        log("c08-10", "2026-03-12T17:00:05Z", "edge-gateway", "Retry scheduled", {"correlation_id": cid}),
        log("c08-11", "2026-03-12T17:00:01Z", "market-data", "Reference price fetched", {"correlation_id": cid}),
        log("c08-12", "2026-03-12T17:00:03Z", "reg-reporting", "Trade report queued", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_08",
        process_context=ProcessContext(
            process_name="fintech_settlement",
            expected_sequence=["trade_match", "aml_screening", "settlement_batch", "custodian_transfer"],
        ),
        raw_logs=core + noiseLogs("c08", cid, 17, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="aml_screening",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c08-02", "c08-06"],
            required_evidence_ids=["c08-02", "c08-06", "c08-03"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="downstream_error_looks_like_root",
                divergence_step="custodian_transfer",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c08-04"],
                decoy_evidence_ids=["c08-04", "c08-05", "c08-10"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="agent",
            domain="fintech",
            difficulty_factors=factors(log_noise=2, causal_distance=3, competing_hypotheses=2, evidence_dispersion=3, metadata_conflict=0, temporal_ambiguity=3),
        ),
    )


def _case09() -> EvalCase:
    """Decoy: duplicate fraud event suggests race; true root is duplicate at fraud_score."""
    cid = "txn-1107"
    core = [
        log("c09-01", "2026-03-12T18:00:00Z", "auth-gateway", "Auth request received", {"correlation_id": cid}),
        log("c09-02", "2026-03-12T18:00:01Z", "fraud-service", "Score computed", {"correlation_id": cid}),
        log("c09-03", "2026-03-12T18:00:01Z", "fraud-service", "Duplicate score event consumed", {"correlation_id": cid}),
        log("c09-04", "2026-03-12T18:00:02Z", "issuer-network", "Approval delayed: conflicting risk signals", {"correlation_id": cid}),
        log("c09-05", "2026-03-12T18:00:03Z", "ledger-service", "Hold not created", {"correlation_id": cid}),
        log("c09-06", "2026-03-12T18:00:04Z", "support-bot", "Customer saw duplicate charge attempt", {"correlation_id": cid}),
        log("c09-07", "2026-03-12T18:00:02Z", "audit-service", "Two fraud events within 50ms", {"correlation_id": cid}),
        log("c09-08", "2026-03-12T18:00:03Z", "issuer-network", "Issuer reports duplicate authorization request", {"correlation_id": cid}),
        log("c09-09", "2026-03-12T18:00:00Z", "edge-gateway", "Card present", {"correlation_id": cid}),
        log("c09-10", "2026-03-12T18:00:04Z", "token-service", "Token vault lookup ok", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_09",
        process_context=ProcessContext(
            process_name="fintech_card_auth",
            expected_sequence=["auth_request", "fraud_score", "issuer_approve", "ledger_hold"],
        ),
        raw_logs=core + noiseLogs("c09", cid, 18, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="fraud_score",
            root_cause_category=RootCauseCategory.RACE_CONDITION,
            culprit_log_ids=["c09-03", "c09-07"],
            required_evidence_ids=["c09-03", "c09-07", "c09-04"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="duplicate_false_diagnosis",
                divergence_step="issuer_approve",
                root_cause_category=RootCauseCategory.DUPLICATE_PROCESSING,
                culprit_log_ids=["c09-08"],
                decoy_evidence_ids=["c09-08", "c09-06", "c09-10"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="fintech",
            difficulty_factors=factors(log_noise=2, causal_distance=2, competing_hypotheses=3, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=1),
        ),
    )


def _case10() -> EvalCase:
    """Hard: KYC skip with webhook timeout decoy."""
    cid = "txn-9903"
    core = [
        log("c10-01", "2026-03-12T19:00:00Z", "kyc-service", "Verification bypassed for renewal window", {"correlation_id": cid}),
        log("c10-02", "2026-03-12T19:00:01Z", "batch-service", "Batch closed", {"correlation_id": cid}),
        log("c10-03", "2026-03-12T19:00:02Z", "webhook-service", "Dispatch deferred pending KYC token", {"correlation_id": cid}),
        log("c10-04", "2026-03-12T19:00:05Z", "webhook-service", "Dispatch timeout after retries", {"correlation_id": cid, "level": "ERROR"}),
        log("c10-05", "2026-03-12T19:00:06Z", "ledger-service", "Credit missing", {"correlation_id": cid}),
        log("c10-06", "2026-03-12T19:00:01Z", "audit-service", "KYC token absent", {"correlation_id": cid, "level": "DEBUG"}),
        log("c10-07", "2026-03-12T19:00:04Z", "support-bot", "Merchant settlement delayed", {"correlation_id": cid}),
        log("c10-08", "2026-03-12T19:00:03Z", "reconciliation-service", "Batch totals balanced", {"correlation_id": cid}),
        log("c10-09", "2026-03-12T19:00:02Z", "risk-service", "Merchant tier stable", {"correlation_id": cid}),
        log("c10-10", "2026-03-12T19:00:05Z", "partner-ledger", "Partner ACK not received", {"correlation_id": cid}),
        log("c10-11", "2026-03-12T19:00:04Z", "analytics-service", "Webhook retry budget exhausted", {"correlation_id": cid}),
        log("c10-12", "2026-03-12T19:00:03Z", "ops-dashboard", "Settlement queue depth nominal", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_10",
        process_context=ProcessContext(
            process_name="fintech_merchant_settlement",
            expected_sequence=["kyc_verify", "batch_close", "webhook_dispatch", "ledger_credit"],
        ),
        raw_logs=core + noiseLogs("c10", cid, 19, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="kyc_verify",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c10-01", "c10-06"],
            required_evidence_ids=["c10-01", "c10-06", "c10-03"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="downstream_error_looks_like_root",
                divergence_step="webhook_dispatch",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c10-04"],
                decoy_evidence_ids=["c10-04", "c10-07", "c10-11"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="agent",
            domain="fintech",
            difficulty_factors=factors(log_noise=2, causal_distance=3, competing_hypotheses=2, evidence_dispersion=3, metadata_conflict=0, temporal_ambiguity=1),
        ),
    )


def _case11() -> EvalCase:
    cid = "prov-7711"
    core = [
        log("c11-06", "2026-03-12T20:00:05Z", "email-service", "Welcome email never triggered", {"correlation_id": cid}),
        log("c11-02", "2026-03-12T20:00:01Z", "tenant-service", "Tenant created", {"correlation_id": cid}),
        log("c11-01", "2026-03-12T20:00:00Z", "contract-service", "Contract signed", {"correlation_id": cid}),
        log("c11-05", "2026-03-12T20:00:04Z", "seat-service", "Seat allocation skipped: tenant flag inactive", {"correlation_id": cid}),
        log("c11-04", "2026-03-12T20:00:03Z", "audit-service", "Tenant marked inactive pending billing sync", {"correlation_id": cid}),
        log("c11-03", "2026-03-12T20:00:02Z", "billing-service", "Billing profile pending", {"correlation_id": cid}),
        log("c11-07", "2026-03-12T20:00:06Z", "support-bot", "Customer cannot log in", {"correlation_id": cid}),
        log("c11-08", "2026-03-12T20:00:02Z", "edge-gateway", "Provisioning workflow started", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_11",
        process_context=ProcessContext(
            process_name="b2b_saas_provisioning",
            expected_sequence=["contract_signed", "tenant_create", "seat_allocate", "welcome_email"],
        ),
        raw_logs=core + noiseLogs("c11", cid, 20, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="seat_allocate",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c11-05", "c11-04"],
            required_evidence_ids=["c11-04", "c11-05", "c11-06"],
        ),
        meta=CaseMeta(
            failure_pattern="out_of_order_delivery",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=2),
        ),
    )


def _case12() -> EvalCase:
    """Hard: SSO silent skip with workspace timeout cascade decoy."""
    cid = "prov-6620"
    core = [
        log("c12-01", "2026-03-12T21:00:00Z", "sso-gateway", "Callback not persisted: session store write failed silently", {"correlation_id": cid}),
        log("c12-02", "2026-03-12T21:00:01Z", "identity-service", "Mapping used cached stale subject", {"correlation_id": cid}),
        log("c12-03", "2026-03-12T21:00:02Z", "role-service", "Role assignment attempted", {"correlation_id": cid}),
        log("c12-04", "2026-03-12T21:00:05Z", "workspace-service", "Grant API timeout", {"correlation_id": cid, "level": "ERROR"}),
        log("c12-05", "2026-03-12T21:00:06Z", "support-bot", "User sees empty workspace", {"correlation_id": cid}),
        log("c12-06", "2026-03-12T21:00:00Z", "audit-service", "No callback receipt stored", {"correlation_id": cid, "level": "DEBUG"}),
        log("c12-07", "2026-03-12T21:00:03Z", "notification-service", "Onboarding email sent prematurely", {"correlation_id": cid}),
        log("c12-08", "2026-03-12T21:00:04Z", "directory-service", "Directory sync reports user exists", {"correlation_id": cid}),
        log("c12-09", "2026-03-12T21:00:01Z", "edge-gateway", "SSO flow started", {"correlation_id": cid}),
        log("c12-10", "2026-03-12T21:00:05Z", "ops-bot", "Auto-retry on workspace grant", {"correlation_id": cid}),
        log("c12-11", "2026-03-12T21:00:02Z", "identity-service", "Subject hash differs from callback token", {"correlation_id": cid, "level": "DEBUG"}),
        log("c12-12", "2026-03-12T21:00:03Z", "workspace-service", "Workspace API latency spike", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_12",
        process_context=ProcessContext(
            process_name="b2b_saas_sso_onboarding",
            expected_sequence=["sso_callback", "identity_map", "role_assign", "workspace_grant"],
        ),
        raw_logs=core + noiseLogs("c12", cid, 21, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="sso_callback",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c12-01", "c12-06"],
            required_evidence_ids=["c12-01", "c12-06", "c12-11"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="upstream_silent_downstream_cascade",
                divergence_step="workspace_grant",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c12-04"],
                decoy_evidence_ids=["c12-04", "c12-05", "c12-12", "c12-10"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="agent",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=2, causal_distance=3, competing_hypotheses=2, evidence_dispersion=3, metadata_conflict=1, temporal_ambiguity=1),
        ),
    )


def _case13() -> EvalCase:
    cid = "prov-5533"
    core = [
        log("c13-01", "2026-03-12T22:00:00Z", "trial-service", "Trial expired", {"correlation_id": cid}),
        log("c13-02", "2026-03-12T22:00:01Z", "plan-service", "Plan selected", {"correlation_id": cid}),
        log("c13-03", "2026-03-12T22:00:02Z", "billing-service", "Payment method attach skipped", {"correlation_id": cid}),
        log("c13-04", "2026-03-12T22:00:03Z", "feature-service", "Unlock rejected: billing profile missing", {"correlation_id": cid}),
        log("c13-05", "2026-03-12T22:00:04Z", "support-bot", "Customer stuck on upgrade screen", {"correlation_id": cid}),
        log("c13-06", "2026-03-12T22:00:02Z", "audit-service", "No billing token recorded", {"correlation_id": cid}),
        log("c13-07", "2026-03-12T22:00:01Z", "notification-service", "Upgrade nudge sent", {"correlation_id": cid}),
        log("c13-08", "2026-03-12T22:00:00Z", "edge-gateway", "Upgrade initiated", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_13",
        process_context=ProcessContext(
            process_name="b2b_saas_trial_conversion",
            expected_sequence=["trial_expire", "plan_select", "billing_attach", "feature_unlock"],
        ),
        raw_logs=core + noiseLogs("c13", cid, 22, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="billing_attach",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c13-03", "c13-06"],
            required_evidence_ids=["c13-03", "c13-06", "c13-04"],
        ),
        meta=CaseMeta(
            failure_pattern="sequence_insufficient",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=1, causal_distance=2, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=0),
        ),
    )


def _case14() -> EvalCase:
    """Decoy: duplicate job vs metadata/message conflict on aggregation."""
    cid = "prov-4421"
    core = [
        log("c14-01", "2026-03-12T23:00:00Z", "meter-service", "Usage collected", {"correlation_id": cid}),
        log("c14-02", "2026-03-12T23:00:01Z", "aggregate-service", "Aggregation complete", {"correlation_id": cid, "billing_state": "skipped"}),
        log("c14-03", "2026-03-12T23:00:02Z", "invoice-service", "Invoice generated", {"correlation_id": cid}),
        log("c14-04", "2026-03-12T23:00:03Z", "delivery-service", "Invoice emailed", {"correlation_id": cid}),
        log("c14-05", "2026-03-12T23:00:04Z", "support-bot", "Customer billed wrong amount", {"correlation_id": cid}),
        log("c14-06", "2026-03-12T23:00:01Z", "audit-service", "Aggregation used stale window", {"correlation_id": cid, "level": "DEBUG"}),
        log("c14-07", "2026-03-12T23:00:02Z", "reprocess-service", "Duplicate aggregation job detected", {"correlation_id": cid}),
        log("c14-08", "2026-03-12T23:00:03Z", "billing-service", "Invoice total matches generated PDF", {"correlation_id": cid, "internal_state": "draft_only"}),
        log("c14-09", "2026-03-12T23:00:00Z", "edge-gateway", "Billing cycle started", {"correlation_id": cid}),
        log("c14-10", "2026-03-12T23:00:04Z", "tax-service", "Tax line items computed", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_14",
        process_context=ProcessContext(
            process_name="b2b_saas_usage_billing",
            expected_sequence=["usage_collect", "usage_aggregate", "invoice_generate", "invoice_deliver"],
        ),
        raw_logs=core + noiseLogs("c14", cid, 23, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="usage_aggregate",
            root_cause_category=RootCauseCategory.METADATA_MESSAGE_CONFLICT,
            culprit_log_ids=["c14-02", "c14-06"],
            required_evidence_ids=["c14-02", "c14-06", "c14-05"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="services_disagree_duplicate_signal",
                divergence_step="usage_aggregate",
                root_cause_category=RootCauseCategory.DUPLICATE_PROCESSING,
                culprit_log_ids=["c14-07"],
                decoy_evidence_ids=["c14-07", "c14-08", "c14-05"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="standard",
            baseline_hypothesis="agent",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=2, causal_distance=2, competing_hypotheses=3, evidence_dispersion=2, metadata_conflict=3, temporal_ambiguity=0),
        ),
    )


def _case15() -> EvalCase:
    """Hard: silent entitlement divergence — success everywhere, root hidden in DEBUG + metadata."""
    cid = "prov-3310"
    core = [
        log("c15-01", "2026-03-13T08:00:00Z", "contract-service", "Contract signed for tenant T-4421", {"correlation_id": cid}),
        log("c15-02", "2026-03-13T08:00:01Z", "entitlement-service", "Entitlement hash mismatch: expected v3, cache v2", {"correlation_id": cid, "level": "DEBUG"}),
        log("c15-03", "2026-03-13T08:00:02Z", "provision-worker", "Tenant provisioning complete for tenant T-4421", {"correlation_id": cid, "provision_state": "deferred"}),
        log("c15-04", "2026-03-13T08:00:03Z", "seat-service", "Seat activation skipped: entitlement not ready", {"correlation_id": cid}),
        log("c15-05", "2026-03-13T08:00:04Z", "support-bot", "Customer says seats never activated", {"correlation_id": cid}),
        log("c15-06", "2026-03-13T08:00:01Z", "audit-service", "Contract event not observed by entitlement service", {"correlation_id": cid}),
        log("c15-07", "2026-03-13T08:00:02Z", "notification-service", "Provisioning success email sent", {"correlation_id": cid}),
        log("c15-08", "2026-03-13T08:00:03Z", "billing-service", "Subscription marked active", {"correlation_id": cid}),
        log("c15-09", "2026-03-13T08:00:00Z", "edge-gateway", "Provisioning workflow accepted", {"correlation_id": cid}),
        log("c15-10", "2026-03-13T08:00:04Z", "ops-bot", "No error alerts raised", {"correlation_id": cid}),
        log("c15-11", "2026-03-13T08:00:02Z", "health-service", "All dependency checks green", {"correlation_id": cid}),
        log("c15-12", "2026-03-13T08:00:03Z", "crm-sync", "Account status synced as active", {"correlation_id": cid}),
        log("c15-13", "2026-03-13T08:00:01Z", "contract-service", "Contract PDF archived", {"correlation_id": cid}),
        log("c15-14", "2026-03-13T08:00:02Z", "analytics-service", "Activation funnel silent drop", {"correlation_id": cid}),
        log("c15-15", "2026-03-13T08:00:03Z", "license-service", "License count unchanged", {"correlation_id": cid, "level": "DEBUG"}),
    ]
    return EvalCase(
        case_id="case_15",
        process_context=ProcessContext(
            process_name="b2b_saas_entitlement_provisioning",
            expected_sequence=["contract_signed", "entitlement_sync", "tenant_provision", "seat_activate"],
        ),
        raw_logs=core + noiseLogs("c15", cid, 8, 0, 6),
        ground_truth=GroundTruth(
            divergence_step="entitlement_sync",
            root_cause_category=RootCauseCategory.ENTITLEMENT_MISMATCH,
            culprit_log_ids=["c15-02"],
            required_evidence_ids=["c15-02", "c15-03", "c15-06", "c15-15"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="success_message_contradicts_metadata",
                divergence_step="tenant_provision",
                root_cause_category=RootCauseCategory.FALSE_SUCCESS_SIGNAL,
                culprit_log_ids=["c15-03"],
                decoy_evidence_ids=["c15-03", "c15-07", "c15-11"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="silent_divergence",
            difficulty="hard",
            baseline_hypothesis="agent",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=3, causal_distance=3, competing_hypotheses=2, evidence_dispersion=3, metadata_conflict=3, temporal_ambiguity=1),
        ),
    )


def writeCases(outputDir: Path | None = None) -> list[EvalCase]:
    directory = outputDir or OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    cases = buildCases()
    validIds = {case.case_id for case in cases}
    for path in directory.glob("case_*.json"):
        if path.stem not in validIds:
            path.unlink()
    for case in cases:
        path = directory / f"{case.case_id}.json"
        path.write_text(
            json.dumps(case.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
    return cases


def printSummary(cases: list[EvalCase]) -> None:
    print(f"Generated {len(cases)} cases in {OUTPUT_DIR}")
    print(
        f"{'Case':<10} {'Domain':<12} {'Pattern':<28} {'Diff':<8} "
        f"{'Logs':<6} {'Decoy':<6} {'Hypothesis':<12} {'Complexity':<10}"
    )
    print("-" * 100)
    for case in cases:
        hasDecoy = "yes" if case.ground_truth.decoy_diagnosis else "no"
        complexity = case.meta.difficulty_factors.composite_score
        print(
            f"{case.case_id:<10} "
            f"{case.meta.domain:<12} "
            f"{case.meta.failure_pattern:<28} "
            f"{case.meta.difficulty:<8} "
            f"{len(case.raw_logs):<6} "
            f"{hasDecoy:<6} "
            f"{case.meta.baseline_hypothesis:<12} "
            f"{complexity:<10}"
        )


def main() -> None:
    cases = writeCases()
    printSummary(cases)


if __name__ == "__main__":
    main()
