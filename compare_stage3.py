#!/usr/bin/env python3
"""Compare Track A Stage 3 results against frozen Stage 0 baseline from a prior eval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.case_loader import getValidLogIds, loadAllCases
from shared.scoring import investigationQualityScore, scoreInvestigation
from shared.schemas import InvestigationResult

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def loadStagePredictions(path: Path, stage: int) -> dict[str, InvestigationResult]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions: dict[str, InvestigationResult] = {}
    for caseId, stageEntries in payload.get("cases", {}).items():
        stageKey = f"stage_{stage}"
        if stageKey not in stageEntries:
            continue
        predictions[caseId] = InvestigationResult.model_validate(stageEntries[stageKey]["prediction"])
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Stage 3 vs frozen Stage 0")
    parser.add_argument("--input", default=str(RESULTS_DIR / "eval_latest.json"))
    parser.add_argument("--baseline-stage", type=int, default=0)
    parser.add_argument("--candidate-stage", type=int, default=3)
    args = parser.parse_args()

    inputPath = Path(args.input)
    baselinePreds = loadStagePredictions(inputPath, args.baseline_stage)
    candidatePreds = loadStagePredictions(inputPath, args.candidate_stage)
    cases = {case.case_id: case for case in loadAllCases()}

    baselineScores = []
    candidateScores = []
    print(f"Comparing stage {args.candidate_stage} vs frozen stage {args.baseline_stage} ({inputPath.name})\n")
    print(f"{'Case':<8} {'Stg0':>7} {'Stg3':>7} {'Delta':>7}")
    print("-" * 34)
    for caseId in sorted(baselinePreds):
        if caseId not in candidatePreds:
            continue
        case = cases[caseId]
        validIds = getValidLogIds(case)
        s0 = scoreInvestigation(baselinePreds[caseId], case.ground_truth, validIds)
        s3 = scoreInvestigation(candidatePreds[caseId], case.ground_truth, validIds)
        baselineScores.append(s0)
        candidateScores.append(s3)
        delta = (s3.total - s0.total) * 100
        print(f"{caseId:<8} {s0.total*100:6.1f}% {s3.total*100:6.1f}% {delta:+6.1f}")

    bMean = investigationQualityScore(baselineScores)
    cMean = investigationQualityScore(candidateScores)
    print("-" * 34)
    print(f"{'MEAN':<8} {bMean:6.1f} {cMean:6.1f} {cMean - bMean:+6.1f}")
    wins = sum(1 for b, c in zip(baselineScores, candidateScores) if c.total > b.total)
    losses = sum(1 for b, c in zip(baselineScores, candidateScores) if c.total < b.total)
    ties = len(baselineScores) - wins - losses
    print(f"\nStage 3 wins: {wins} | losses: {losses} | ties: {ties}")


if __name__ == "__main__":
    main()
