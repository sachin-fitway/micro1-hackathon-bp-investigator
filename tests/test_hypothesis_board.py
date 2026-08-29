"""Tests for hypothesis board assembly (Track A)."""

from __future__ import annotations

from agents.hypothesis_board import assembleStage3Board, buildDecoyCandidate, mergeCandidatePools
from generate_data import buildCases
from shared.schemas import HypothesisBoard, HypothesisCandidate, InvestigationResult, RootCauseCategory


def _candidate(
    hypothesisId: str,
    source: str,
    step: str,
    category: RootCauseCategory,
) -> HypothesisCandidate:
    return HypothesisCandidate(
        hypothesis_id=hypothesisId,
        source=source,  # type: ignore[arg-type]
        divergence_step=step,
        root_cause_category=category,
        culprit_log_ids=["log-1"],
        evidence_log_ids=["log-1"],
        supporting_evidence=["log-1"],
        contradicting_evidence=["log-2"],
        earlier_explanation="Earlier step may explain this.",
        explanation="test",
    )


def testAssembleStage3BoardPreservesBaselineAndDecoy():
    case = next(item for item in buildCases() if item.ground_truth.decoy_diagnosis is not None)
    baseline = InvestigationResult(
        divergence_step=case.ground_truth.divergence_step,
        root_cause_category=RootCauseCategory.SEQUENCE_SKIP,
        culprit_log_ids=["log-x"],
        evidence_log_ids=["log-x"],
        explanation="baseline",
    )
    ruleBoard = HypothesisBoard(
        leading_hypothesis_id="hypothesis_downstream",
        candidates=[
            _candidate(
                "hypothesis_downstream",
                "rule_checker",
                "issuer_approve",
                RootCauseCategory.DUPLICATE_PROCESSING,
            ),
            _candidate(
                "hypothesis_upstream",
                "rule_checker",
                case.ground_truth.divergence_step,
                RootCauseCategory.RACE_CONDITION,
            ),
        ],
    )
    board = assembleStage3Board(case, ruleBoard, baseline)
    ids = {item.hypothesis_id for item in board.candidates}
    assert "baseline" in ids
    assert "decoy_trap" in ids
    assert len(board.candidates) >= 3


def testMergeCandidatePoolsDedupesByIdAndStepCategory():
    first = _candidate("a", "rule_checker", "step_a", RootCauseCategory.SEQUENCE_SKIP)
    duplicate = _candidate("b", "rule_checker", "step_a", RootCauseCategory.SEQUENCE_SKIP)
    merged = mergeCandidatePools([first], [duplicate])
    assert len(merged) == 1


def testBuildDecoyCandidateUsesDecoyFields():
    case = next(item for item in buildCases() if item.ground_truth.decoy_diagnosis is not None)
    decoy = case.ground_truth.decoy_diagnosis
    assert decoy is not None
    candidate = buildDecoyCandidate(decoy)
    assert candidate.hypothesis_id == "decoy_trap"
    assert candidate.divergence_step == decoy.divergence_step
    assert candidate.source == "decoy_trap"
