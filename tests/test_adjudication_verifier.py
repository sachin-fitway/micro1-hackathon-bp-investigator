"""Tests for adjudication verifier normalization."""

from __future__ import annotations

from agents.adjudication_verifier import applyDeterministicAdjudication
from generate_data import buildCases
from shared.schemas import (
    CausalComparison,
    HypothesisAssessment,
    InvestigationResult,
    RootCauseCategory,
    VerifierAdjudicationOutcome,
)

ORDER_SEQUENCE = ["payment_authorize", "order_confirm", "inventory_reserve"]


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


def _outcome(decision: str, whySelected: str, selected: InvestigationResult) -> VerifierAdjudicationOutcome:
    return VerifierAdjudicationOutcome(
        decision=decision,  # type: ignore[arg-type]
        selected_hypothesis=selected,
        baseline_assessment=HypothesisAssessment(valid=True, problems=[]),
        challenger_assessment=HypothesisAssessment(valid=True, problems=[]),
        comparison=CausalComparison(
            baseline_causal_chain=["baseline chain"],
            challenger_causal_chain=["challenger chain"],
            why_selected=whySelected,
        ),
        confidence=0.8,
    )


def testApplyDeterministicAdjudicationForcesKeepBaselineCase02():
    case = next(item for item in buildCases() if item.case_id == "case_02")
    baseline = _result("order_confirm", RootCauseCategory.SEQUENCE_SKIP, ["c02-07"], ["c02-07", "c02-08"])
    challenger = _result(
        "payment_authorize",
        RootCauseCategory.FALSE_SUCCESS_SIGNAL,
        ["c02-06"],
        ["c02-06", "c02-07"],
    )
    outcome = applyDeterministicAdjudication(
        _outcome("override_baseline", "Log c02-06 shows authorization succeeded falsely.", challenger),
        case,
        baseline,
        challenger,
        ORDER_SEQUENCE,
        [],
        [],
        {"c02-06", "c02-07", "c02-08"},
    )
    assert outcome.decision == "keep_baseline"
    assert outcome.selected_hypothesis.divergence_step == "order_confirm"
    assert any("SEQUENCE_SKIP_PRIORITY" in block for block in outcome.deterministic_blocks)


def testApplyDeterministicAdjudicationBlocksSameStepSupportPromotion():
    case = next(item for item in buildCases() if item.case_id == "case_15")
    baseline = _result(
        "entitlement_sync",
        RootCauseCategory.WEBHOOK_MISSING,
        ["c15-06"],
        ["c15-06", "c15-02"],
    )
    challenger = _result(
        "entitlement_sync",
        RootCauseCategory.CONFIG_DRIFT,
        ["c15-02"],
        ["c15-02", "c15-06", "c15-03"],
    )
    outcome = applyDeterministicAdjudication(
        _outcome("override_baseline", "Log c15-02 shows hash mismatch.", challenger),
        case,
        baseline,
        challenger,
        case.process_context.expected_sequence,
        [],
        [],
        {log.log_id for log in case.raw_logs},
    )
    assert outcome.decision == "keep_baseline"
    assert any("SAME_STEP_CAUSAL_ROLE" in block for block in outcome.deterministic_blocks)
