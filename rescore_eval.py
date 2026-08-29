#!/usr/bin/env python3
"""Re-score saved eval results after taxonomy/scoring changes (no LLM calls)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.case_loader import getValidLogIds, loadAllCases
from shared.root_cause_taxonomy import rootCauseMatchLabel, scoreRootCauseMatch
from shared.scoring import investigationQualityScore, scoreInvestigation
from shared.schemas import GroundTruth, InvestigationResult, RootCauseCategory, ScoreBreakdown
from workflows.ablation import STAGE_LABELS

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def strictScoreRootCause(predicted: InvestigationResult, groundTruth: GroundTruth) -> float:
    if predicted.root_cause_category == groundTruth.root_cause_category:
        return 1.0
    return 0.0


def strictScoreInvestigation(
    predicted: InvestigationResult,
    groundTruth: GroundTruth,
    validLogIds: set[str],
) -> ScoreBreakdown:
    from shared.scoring import (
        scoreEvidencePrecision,
        scoreEvidenceRecall,
        scoreFailurePoint,
        scoreNoFabricated,
        WEIGHT_EVIDENCE_PRECISION,
        WEIGHT_EVIDENCE_RECALL,
        WEIGHT_FAILURE_POINT,
        WEIGHT_NO_FABRICATED,
        WEIGHT_ROOT_CAUSE,
    )

    failurePoint = scoreFailurePoint(predicted, groundTruth)
    rootCause = strictScoreRootCause(predicted, groundTruth)
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


def loadPredictions(path: Path) -> dict[str, dict[int, InvestigationResult]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions: dict[str, dict[int, InvestigationResult]] = {}
    for caseId, stageEntries in payload.get("cases", {}).items():
        for stageKey, entry in stageEntries.items():
            stage = int(stageKey.removeprefix("stage_"))
            predictions.setdefault(caseId, {})[stage] = InvestigationResult.model_validate(
                entry["prediction"]
            )
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score eval_latest.json with current rubric")
    parser.add_argument(
        "--input",
        default=str(RESULTS_DIR / "eval_latest.json"),
        help="Path to saved eval JSON",
    )
    parser.add_argument("--cases", default="", help="Comma-separated case IDs to highlight")
    args = parser.parse_args()

    inputPath = Path(args.input)
    predictions = loadPredictions(inputPath)
    cases = {case.case_id: case for case in loadAllCases()}
    highlight = {part.strip() for part in args.cases.split(",") if part.strip()}

    stageScoresStrict: dict[int, list[ScoreBreakdown]] = {}
    stageScoresTolerant: dict[int, list[ScoreBreakdown]] = {}

    print(f"Re-scoring {inputPath.name} ({len(predictions)} cases)\n")
    print("Stage means (IQS %):")
    print(f"{'Stage':<6} {'Strict':>8} {'Tolerant':>10}  Description")
    print("-" * 60)

    for caseId in sorted(predictions):
        case = cases[caseId]
        validIds = getValidLogIds(case)
        for stage, prediction in sorted(predictions[caseId].items()):
            strict = strictScoreInvestigation(prediction, case.ground_truth, validIds)
            tolerant = scoreInvestigation(prediction, case.ground_truth, validIds)
            stageScoresStrict.setdefault(stage, []).append(strict)
            stageScoresTolerant.setdefault(stage, []).append(tolerant)

            if highlight and caseId in highlight:
                label = rootCauseMatchLabel(prediction.root_cause_category, case.ground_truth)
                print(
                    f"  {caseId} stage {stage}: strict={strict.total*100:.1f}% "
                    f"tolerant={tolerant.total*100:.1f}% "
                    f"cause={prediction.root_cause_category.value} "
                    f"({label}, cause_pts={tolerant.root_cause:.1f})"
                )

    for stage in sorted(stageScoresTolerant):
        strictMean = investigationQualityScore(stageScoresStrict[stage])
        tolerantMean = investigationQualityScore(stageScoresTolerant[stage])
        print(f"{stage:<6} {strictMean:>8.1f} {tolerantMean:>10.1f}  {STAGE_LABELS[stage]}")

    print("\nRoot-cause partial credit applies only within documented equivalence groups")
    print("(see shared/root_cause_taxonomy.py). Wrong divergence_step is never partial.")


if __name__ == "__main__":
    main()
