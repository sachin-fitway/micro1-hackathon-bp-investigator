#!/usr/bin/env python3
"""Generate unseen holdout benchmark cases (case_16+) — independent of development set."""

from __future__ import annotations

import json
from pathlib import Path

from generate_data import factors, log, noiseLogs
from shared.schemas import (
    CaseMeta,
    DecoyDiagnosis,
    EvalCase,
    GroundTruth,
    ProcessContext,
    RootCauseCategory,
)

HOLDOUT_DIR = Path(__file__).resolve().parent / "data" / "holdout"
HOLDOUT_CASE_IDS = tuple(f"case_{index}" for index in range(16, 24))


def buildHoldoutCases() -> list[EvalCase]:
    return [
        _case16(),
        _case17(),
        _case18(),
        _case19(),
        _case20(),
        _case21(),
        _case22(),
        _case23(),
    ]


def _case16() -> EvalCase:
    """Healthcare prior auth — entitlement mismatch, silent success metadata."""
    cid = "pa-4401"
    core = [
        log("c16-01", "2026-04-02T09:00:00Z", "referral-gateway", "Referral accepted", {"correlation_id": cid}),
        log("c16-02", "2026-04-02T09:00:01Z", "coverage-service", "Coverage verified", {"correlation_id": cid, "plan_tier": "basic", "required_tier": "specialist"}),
        log("c16-03", "2026-04-02T09:00:02Z", "auth-service", "Prior auth submission blocked: plan insufficient", {"correlation_id": cid}),
        log("c16-04", "2026-04-02T09:00:03Z", "scheduling-service", "Appointment slot held without auth", {"correlation_id": cid}),
        log("c16-05", "2026-04-02T09:00:04Z", "support-portal", "Patient told authorization pending", {"correlation_id": cid}),
        log("c16-06", "2026-04-02T09:00:01Z", "audit-service", "Member plan tier basic; referral requires specialist", {"correlation_id": cid, "level": "DEBUG"}),
        log("c16-07", "2026-04-02T09:00:02Z", "fhir-adapter", "Coverage snapshot cached from yesterday", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_16",
        process_context=ProcessContext(
            process_name="healthcare_prior_auth",
            expected_sequence=["referral_intake", "coverage_verify", "prior_auth_submit", "care_schedule"],
        ),
        raw_logs=core + noiseLogs("c16", cid, 9, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="coverage_verify",
            root_cause_category=RootCauseCategory.ENTITLEMENT_MISMATCH,
            culprit_log_ids=["c16-02", "c16-06"],
            required_evidence_ids=["c16-02", "c16-06", "c16-03"],
        ),
        meta=CaseMeta(
            failure_pattern="silent_divergence",
            difficulty="hard",
            baseline_hypothesis="either",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=1, causal_distance=2, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=3, temporal_ambiguity=0),
        ),
    )


def _case17() -> EvalCase:
    """Logistics cross-dock — webhook missing with carrier ERROR decoy."""
    cid = "xd-8820"
    core = [
        log("c17-01", "2026-04-02T10:00:00Z", "dock-service", "Inbound pallet scanned", {"correlation_id": cid}),
        log("c17-02", "2026-04-02T10:00:01Z", "customs-service", "Customs clearance recorded", {"correlation_id": cid}),
        log("c17-03", "2026-04-02T10:00:02Z", "transfer-service", "Cross-dock move initiated", {"correlation_id": cid}),
        log("c17-04", "2026-04-02T10:00:03Z", "audit-service", "No carrier handoff webhook received", {"correlation_id": cid, "level": "DEBUG"}),
        log("c17-05", "2026-04-02T10:00:06Z", "carrier-api", "Dispatch API timeout", {"correlation_id": cid, "level": "ERROR"}),
        log("c17-06", "2026-04-02T10:00:07Z", "support-bot", "Shipment stuck at hub", {"correlation_id": cid}),
        log("c17-07", "2026-04-02T10:00:04Z", "lastmile-service", "Route not created: missing handoff event", {"correlation_id": cid}),
        log("c17-08", "2026-04-02T10:00:05Z", "partner-hub", "Webhook endpoint returned 200 for health check only", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_17",
        process_context=ProcessContext(
            process_name="logistics_cross_dock",
            expected_sequence=["inbound_scan", "customs_clear", "cross_dock_transfer", "last_mile_dispatch"],
        ),
        raw_logs=core + noiseLogs("c17", cid, 10, 0, 5),
        ground_truth=GroundTruth(
            divergence_step="cross_dock_transfer",
            root_cause_category=RootCauseCategory.WEBHOOK_MISSING,
            culprit_log_ids=["c17-04"],
            required_evidence_ids=["c17-04", "c17-07", "c17-03"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="downstream_error_looks_like_root",
                divergence_step="last_mile_dispatch",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c17-05"],
                decoy_evidence_ids=["c17-05", "c17-06", "c17-08"],
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


def _case18() -> EvalCase:
    """Insurance claims — duplicate processing at adjuster assign; issuer decoy."""
    cid = "clm-9912"
    core = [
        log("c18-01", "2026-04-02T11:00:00Z", "claims-intake", "Claim opened", {"correlation_id": cid}),
        log("c18-02", "2026-04-02T11:00:01Z", "policy-service", "Policy active for member", {"correlation_id": cid}),
        log("c18-03", "2026-04-02T11:00:02Z", "adjuster-queue", "Assignment created", {"correlation_id": cid}),
        log("c18-04", "2026-04-02T11:00:02Z", "adjuster-queue", "Duplicate assignment event replayed", {"correlation_id": cid}),
        log("c18-05", "2026-04-02T11:00:03Z", "payment-service", "Release blocked: conflicting adjuster locks", {"correlation_id": cid}),
        log("c18-06", "2026-04-02T11:00:04Z", "support-bot", "Claim payment delayed", {"correlation_id": cid}),
        log("c18-07", "2026-04-02T11:00:03Z", "audit-service", "Two assignment IDs for same claim within 40ms", {"correlation_id": cid}),
        log("c18-08", "2026-04-02T11:00:04Z", "bank-gateway", "ACH reject: duplicate beneficiary reference", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_18",
        process_context=ProcessContext(
            process_name="insurance_claim_payment",
            expected_sequence=["claim_intake", "policy_validate", "adjuster_assign", "payment_release"],
        ),
        raw_logs=core + noiseLogs("c18", cid, 11, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="adjuster_assign",
            root_cause_category=RootCauseCategory.DUPLICATE_PROCESSING,
            culprit_log_ids=["c18-04", "c18-07"],
            required_evidence_ids=["c18-04", "c18-07", "c18-05"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="duplicate_false_diagnosis",
                divergence_step="payment_release",
                root_cause_category=RootCauseCategory.DUPLICATE_PROCESSING,
                culprit_log_ids=["c18-08"],
                decoy_evidence_ids=["c18-08", "c18-06"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="standard",
            baseline_hypothesis="either",
            domain="fintech",
            difficulty_factors=factors(log_noise=1, causal_distance=2, competing_hypotheses=2, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=1),
        ),
    )


def _case19() -> EvalCase:
    """Manufacturing QC — config drift on recipe load (straightforward)."""
    cid = "bat-2208"
    core = [
        log("c19-01", "2026-04-02T12:00:00Z", "batch-service", "Batch started", {"correlation_id": cid}),
        log("c19-02", "2026-04-02T12:00:01Z", "recipe-service", "Recipe v7 loaded; spec requires v9", {"correlation_id": cid, "recipe_version": "7", "required_version": "9"}),
        log("c19-03", "2026-04-02T12:00:02Z", "mixer-service", "Mix completed with wrong viscosity", {"correlation_id": cid}),
        log("c19-04", "2026-04-02T12:00:03Z", "qc-service", "QC hold: viscosity out of range", {"correlation_id": cid}),
        log("c19-05", "2026-04-02T12:00:04Z", "ops-alert", "Line stopped", {"correlation_id": cid}),
        log("c19-06", "2026-04-02T12:00:01Z", "config-service", "Plant default recipe map stale", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_19",
        process_context=ProcessContext(
            process_name="manufacturing_batch_qc",
            expected_sequence=["batch_start", "recipe_load", "mix_execute", "qc_release"],
        ),
        raw_logs=core + noiseLogs("c19", cid, 12, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="recipe_load",
            root_cause_category=RootCauseCategory.CONFIG_DRIFT,
            culprit_log_ids=["c19-02", "c19-06"],
            required_evidence_ids=["c19-02", "c19-06", "c19-04"],
        ),
        meta=CaseMeta(
            failure_pattern="multiple_plausible_causes",
            difficulty="standard",
            baseline_hypothesis="baseline",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=1, evidence_dispersion=1, metadata_conflict=1, temporal_ambiguity=0),
        ),
    )


def _case20() -> EvalCase:
    """Telecom number port — sequence skip at carrier validate; release timeout decoy."""
    cid = "port-7733"
    core = [
        log("c20-01", "2026-04-02T13:00:00Z", "port-service", "Port request filed", {"correlation_id": cid}),
        log("c20-02", "2026-04-02T13:00:01Z", "carrier-gateway", "Validation bypassed: expedite flag set", {"correlation_id": cid}),
        log("c20-03", "2026-04-02T13:00:02Z", "number-registry", "Release rejected: validation token absent", {"correlation_id": cid}),
        log("c20-04", "2026-04-02T13:00:05Z", "carrier-gateway", "Release polling timeout", {"correlation_id": cid, "level": "ERROR"}),
        log("c20-05", "2026-04-02T13:00:06Z", "support-bot", "Number port failed", {"correlation_id": cid}),
        log("c20-06", "2026-04-02T13:00:01Z", "audit-service", "No carrier validation artifact stored", {"correlation_id": cid, "level": "DEBUG"}),
        log("c20-07", "2026-04-02T13:00:03Z", "account-service", "Account link deferred", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_20",
        process_context=ProcessContext(
            process_name="telecom_number_port",
            expected_sequence=["port_request", "carrier_validate", "number_release", "account_link"],
        ),
        raw_logs=core + noiseLogs("c20", cid, 13, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="carrier_validate",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c20-02", "c20-06"],
            required_evidence_ids=["c20-02", "c20-06", "c20-03"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="downstream_error_looks_like_root",
                divergence_step="number_release",
                root_cause_category=RootCauseCategory.TIMEOUT_STALL,
                culprit_log_ids=["c20-04"],
                decoy_evidence_ids=["c20-04", "c20-05"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="decoy_diagnosis",
            difficulty="hard",
            baseline_hypothesis="agent",
            domain="fintech",
            difficulty_factors=factors(log_noise=2, causal_distance=2, competing_hypotheses=2, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=1),
        ),
    )


def _case21() -> EvalCase:
    """Marketplace payout — metadata/message conflict on fee calculation (ambiguous)."""
    cid = "mkt-5518"
    core = [
        log("c21-01", "2026-04-02T14:00:00Z", "order-ledger", "Order settled", {"correlation_id": cid}),
        log("c21-02", "2026-04-02T14:00:01Z", "fee-engine", "Fees calculated successfully", {"correlation_id": cid, "fee_state": "waived", "seller_fee_due": 42.50}),
        log("c21-03", "2026-04-02T14:00:02Z", "payout-service", "Payout blocked: fee balance outstanding", {"correlation_id": cid}),
        log("c21-04", "2026-04-02T14:00:03Z", "receipt-service", "Receipt archived with zero payout", {"correlation_id": cid}),
        log("c21-05", "2026-04-02T14:00:04Z", "support-bot", "Seller not paid", {"correlation_id": cid}),
        log("c21-06", "2026-04-02T14:00:01Z", "audit-service", "Promotional waiver flag not propagated to payout", {"correlation_id": cid}),
        log("c21-07", "2026-04-02T14:00:02Z", "tax-service", "Withholding computed on full fee amount", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_21",
        process_context=ProcessContext(
            process_name="marketplace_seller_payout",
            expected_sequence=["order_settle", "fee_calculate", "seller_payout", "receipt_archive"],
        ),
        raw_logs=core + noiseLogs("c21", cid, 14, 0, 3),
        ground_truth=GroundTruth(
            divergence_step="fee_calculate",
            root_cause_category=RootCauseCategory.METADATA_MESSAGE_CONFLICT,
            culprit_log_ids=["c21-02", "c21-06"],
            required_evidence_ids=["c21-02", "c21-06", "c21-03"],
        ),
        meta=CaseMeta(
            failure_pattern="metadata_message_conflict",
            difficulty="standard",
            baseline_hypothesis="baseline",
            domain="ecommerce",
            difficulty_factors=factors(log_noise=1, causal_distance=1, competing_hypotheses=2, evidence_dispersion=1, metadata_conflict=3, temporal_ambiguity=0),
        ),
    )


def _case22() -> EvalCase:
    """HR onboarding — false success on background check (silent)."""
    cid = "hr-3309"
    core = [
        log("c22-01", "2026-04-02T15:00:00Z", "offer-service", "Offer accepted", {"correlation_id": cid}),
        log("c22-02", "2026-04-02T15:00:01Z", "background-service", "Background check cleared", {"correlation_id": cid, "check_status": "pending_vendor", "report_ready": False}),
        log("c22-03", "2026-04-02T15:00:02Z", "it-provisioning", "Account creation skipped: clearance not verified", {"correlation_id": cid}),
        log("c22-04", "2026-04-02T15:00:03Z", "badge-service", "Badge not issued", {"correlation_id": cid}),
        log("c22-05", "2026-04-02T15:00:04Z", "support-bot", "New hire cannot access systems", {"correlation_id": cid}),
        log("c22-06", "2026-04-02T15:00:01Z", "vendor-api", "Vendor report still queued", {"correlation_id": cid, "level": "DEBUG"}),
        log("c22-07", "2026-04-02T15:00:02Z", "hris-sync", "Employee record created prematurely", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_22",
        process_context=ProcessContext(
            process_name="hr_employee_onboarding",
            expected_sequence=["offer_accept", "background_check", "account_provision", "badge_issue"],
        ),
        raw_logs=core + noiseLogs("c22", cid, 15, 0, 4),
        ground_truth=GroundTruth(
            divergence_step="background_check",
            root_cause_category=RootCauseCategory.FALSE_SUCCESS_SIGNAL,
            culprit_log_ids=["c22-02", "c22-06"],
            required_evidence_ids=["c22-02", "c22-06", "c22-03"],
        ),
        meta=CaseMeta(
            failure_pattern="silent_divergence",
            difficulty="hard",
            baseline_hypothesis="either",
            domain="b2b_saas",
            difficulty_factors=factors(log_noise=2, causal_distance=2, competing_hypotheses=1, evidence_dispersion=2, metadata_conflict=3, temporal_ambiguity=0),
        ),
    )


def _case23() -> EvalCase:
    """Energy dispatch — out-of-order confirm before dispatch executed."""
    cid = "grid-1188"
    core = [
        log("c23-01", "2026-04-02T16:00:00Z", "forecast-service", "Demand forecast published", {"correlation_id": cid}),
        log("c23-02", "2026-04-02T16:00:01Z", "commit-service", "Unit commitment submitted", {"correlation_id": cid}),
        log("c23-04", "2026-04-02T16:00:04Z", "meter-service", "Meter confirmation missing dispatch token", {"correlation_id": cid}),
        log("c23-03", "2026-04-02T16:00:03Z", "dispatch-service", "Dispatch command issued", {"correlation_id": cid}),
        log("c23-05", "2026-04-02T16:00:02Z", "scada-bridge", "Dispatch ack received before command logged", {"correlation_id": cid, "clock_skew_ms": 1500}),
        log("c23-06", "2026-04-02T16:00:05Z", "ops-console", "Grid imbalance alert", {"correlation_id": cid}),
        log("c23-07", "2026-04-02T16:00:03Z", "audit-service", "Confirm step invoked without dispatch completion", {"correlation_id": cid}),
        log("c23-08", "2026-04-02T16:00:01Z", "weather-feed", "Wind forecast updated", {"correlation_id": cid}),
    ]
    return EvalCase(
        case_id="case_23",
        process_context=ProcessContext(
            process_name="energy_grid_dispatch",
            expected_sequence=["demand_forecast", "unit_commit", "dispatch_execute", "meter_confirm"],
        ),
        raw_logs=core + noiseLogs("c23", cid, 16, 0, 5),
        ground_truth=GroundTruth(
            divergence_step="meter_confirm",
            root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
            culprit_log_ids=["c23-04", "c23-07"],
            required_evidence_ids=["c23-03", "c23-04", "c23-07"],
            decoy_diagnosis=DecoyDiagnosis(
                decoy_type="temporal_wrong_causal_order",
                divergence_step="dispatch_execute",
                root_cause_category=RootCauseCategory.RACE_CONDITION,
                culprit_log_ids=["c23-05"],
                decoy_evidence_ids=["c23-05", "c23-06"],
            ),
        ),
        meta=CaseMeta(
            failure_pattern="out_of_order_delivery",
            difficulty="hard",
            baseline_hypothesis="either",
            domain="fintech",
            difficulty_factors=factors(log_noise=2, causal_distance=1, competing_hypotheses=2, evidence_dispersion=2, metadata_conflict=0, temporal_ambiguity=3),
        ),
    )


def writeHoldoutCases(outputDir: Path | None = None) -> list[EvalCase]:
    directory = outputDir or HOLDOUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    cases = buildHoldoutCases()
    validIds = {case.case_id for case in cases}
    for path in directory.glob("case_*.json"):
        if path.stem not in validIds:
            path.unlink()
    for case in cases:
        path = directory / f"{case.case_id}.json"
        path.write_text(json.dumps(case.model_dump(mode="json"), indent=2), encoding="utf-8")
    return cases


def main() -> None:
    cases = writeHoldoutCases()
    print(f"Generated {len(cases)} holdout cases in {HOLDOUT_DIR}")


if __name__ == "__main__":
    main()
