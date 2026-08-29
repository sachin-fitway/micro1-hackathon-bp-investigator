"""Assemble and normalize competing investigation hypotheses."""

from __future__ import annotations

from shared.schemas import (
    DecoyDiagnosis,
    EvalCase,
    HypothesisBoard,
    HypothesisCandidate,
    HypothesisSource,
    InvestigationResult,
)


def investigationToCandidate(
    result: InvestigationResult,
    hypothesisId: str,
    source: HypothesisSource,
    supportingEvidence: list[str] | None = None,
    contradictingEvidence: list[str] | None = None,
    earlierExplanation: str = "",
) -> HypothesisCandidate:
    return HypothesisCandidate(
        hypothesis_id=hypothesisId,
        source=source,
        divergence_step=result.divergence_step,
        root_cause_category=result.root_cause_category,
        culprit_log_ids=list(result.culprit_log_ids),
        evidence_log_ids=list(result.evidence_log_ids),
        supporting_evidence=supportingEvidence or list(result.evidence_log_ids),
        contradicting_evidence=contradictingEvidence or [],
        earlier_explanation=earlierExplanation or result.explanation,
        explanation=result.explanation,
    )


def buildDecoyCandidate(decoy: DecoyDiagnosis) -> HypothesisCandidate:
    return HypothesisCandidate(
        hypothesis_id="decoy_trap",
        source="decoy_trap",
        divergence_step=decoy.divergence_step,
        root_cause_category=decoy.root_cause_category,
        culprit_log_ids=list(decoy.culprit_log_ids),
        evidence_log_ids=list(decoy.decoy_evidence_ids),
        supporting_evidence=list(decoy.decoy_evidence_ids),
        contradicting_evidence=[],
        earlier_explanation=(
            "Downstream symptom logs may appear causal if earlier divergence is ignored."
        ),
        explanation=f"Plausible trap reading ({decoy.decoy_type}).",
    )


def candidateKey(candidate: HypothesisCandidate) -> tuple[str, str]:
    return (candidate.divergence_step.strip().lower(), candidate.root_cause_category.value)


def mergeCandidatePools(*pools: list[HypothesisCandidate]) -> list[HypothesisCandidate]:
    merged: list[HypothesisCandidate] = []
    seenIds: set[str] = set()
    seenKeys: set[tuple[str, str]] = set()
    for pool in pools:
        for candidate in pool:
            if candidate.hypothesis_id in seenIds:
                continue
            key = candidateKey(candidate)
            if key in seenKeys:
                continue
            merged.append(candidate)
            seenIds.add(candidate.hypothesis_id)
            seenKeys.add(key)
    return merged


def assembleStage3Board(
    case: EvalCase,
    ruleCheckerBoard: HypothesisBoard,
    baseline: InvestigationResult,
) -> HypothesisBoard:
    baselineCandidate = investigationToCandidate(
        baseline,
        hypothesisId="baseline",
        source="baseline",
    )
    extraPools: list[list[HypothesisCandidate]] = [[baselineCandidate], list(ruleCheckerBoard.candidates)]
    if case.ground_truth.decoy_diagnosis is not None:
        extraPools.append([buildDecoyCandidate(case.ground_truth.decoy_diagnosis)])
    candidates = mergeCandidatePools(*extraPools)
    leadingId = ruleCheckerBoard.leading_hypothesis_id
    if not any(item.hypothesis_id == leadingId for item in candidates):
        leadingId = candidates[0].hypothesis_id if candidates else "baseline"
    return HypothesisBoard(leading_hypothesis_id=leadingId, candidates=candidates)


def findCandidate(board: HypothesisBoard, hypothesisId: str) -> HypothesisCandidate | None:
    for candidate in board.candidates:
        if candidate.hypothesis_id == hypothesisId:
            return candidate
    return None


def candidateToInvestigation(candidate: HypothesisCandidate) -> InvestigationResult:
    return InvestigationResult(
        divergence_step=candidate.divergence_step,
        root_cause_category=candidate.root_cause_category,
        culprit_log_ids=list(candidate.culprit_log_ids),
        evidence_log_ids=list(candidate.evidence_log_ids),
        explanation=candidate.explanation,
    )
