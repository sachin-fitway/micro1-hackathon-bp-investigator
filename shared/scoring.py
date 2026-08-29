"""Weighted scoring rubric for investigation results."""

from __future__ import annotations

from shared.root_cause_taxonomy import scoreRootCauseMatch
from shared.schemas import GroundTruth, InvestigationResult, ScoreBreakdown

WEIGHT_FAILURE_POINT = 0.35
WEIGHT_ROOT_CAUSE = 0.30
WEIGHT_EVIDENCE_RECALL = 0.15
WEIGHT_EVIDENCE_PRECISION = 0.10
WEIGHT_NO_FABRICATED = 0.10


def _normalizeStep(step: str) -> str:
    return step.strip().lower()


def scoreFailurePoint(predicted: InvestigationResult, groundTruth: GroundTruth) -> float:
    if _normalizeStep(predicted.divergence_step) == _normalizeStep(groundTruth.divergence_step):
        return 1.0
    return 0.0


def scoreRootCause(predicted: InvestigationResult, groundTruth: GroundTruth) -> float:
    return scoreRootCauseMatch(predicted.root_cause_category, groundTruth)


def scoreEvidenceRecall(predicted: InvestigationResult, groundTruth: GroundTruth) -> float:
    required = set(groundTruth.required_evidence_ids)
    if not required:
        return 1.0
    cited = set(predicted.evidence_log_ids)
    return len(cited & required) / len(required)


def scoreEvidencePrecision(predicted: InvestigationResult, groundTruth: GroundTruth) -> float:
    cited = set(predicted.evidence_log_ids)
    if not cited:
        required = set(groundTruth.required_evidence_ids)
        return 1.0 if not required else 0.0
    required = set(groundTruth.required_evidence_ids)
    return len(cited & required) / len(cited)


def scoreNoFabricated(predicted: InvestigationResult, validLogIds: set[str]) -> float:
    citedIds = set(predicted.evidence_log_ids) | set(predicted.culprit_log_ids)
    if not citedIds:
        return 1.0
    if citedIds.issubset(validLogIds):
        return 1.0
    return 0.0


def scoreInvestigation(
    predicted: InvestigationResult,
    groundTruth: GroundTruth,
    validLogIds: set[str],
) -> ScoreBreakdown:
    failurePoint = scoreFailurePoint(predicted, groundTruth)
    rootCause = scoreRootCause(predicted, groundTruth)
    evidenceRecall = scoreEvidenceRecall(predicted, groundTruth)
    evidencePrecision = scoreEvidencePrecision(predicted, groundTruth)
    noFabricated = scoreNoFabricated(predicted, validLogIds)
    total = (
        WEIGHT_FAILURE_POINT * failurePoint
        + WEIGHT_ROOT_CAUSE * rootCause
        + WEIGHT_EVIDENCE_RECALL * evidenceRecall
        + WEIGHT_EVIDENCE_PRECISION * evidencePrecision
        + WEIGHT_NO_FABRICATED * noFabricated
    )
    return ScoreBreakdown(
        failure_point=failurePoint,
        root_cause=rootCause,
        evidence_recall=evidenceRecall,
        evidence_precision=evidencePrecision,
        no_fabricated=noFabricated,
        total=total,
    )


def investigationQualityScore(scores: list[ScoreBreakdown]) -> float:
    if not scores:
        return 0.0
    return sum(score.total for score in scores) / len(scores) * 100
