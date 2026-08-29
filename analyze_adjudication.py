#!/usr/bin/env python3
"""Analyze Stage 3 adjudication results vs Stage 0 and Stage 2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.case_loader import loadCase, getValidLogIds, CASES_DIR, BENCHMARK_CASE_IDS
from shared.scoring import scoreInvestigation, investigationQualityScore
from shared.schemas import InvestigationResult

RESULTS_DIR = Path(__file__).resolve().parent / "results"
TRAJECTORIES_DIR = Path(__file__).resolve().parent / "trajectories"


def loadPredictions(path: Path, stage: int) -> dict[str, InvestigationResult]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions: dict[str, InvestigationResult] = {}
    for caseId, stageEntries in payload.get("cases", {}).items():
        stageKey = f"stage_{stage}"
        if stageKey in stageEntries:
            predictions[caseId] = InvestigationResult.model_validate(
                stageEntries[stageKey]["prediction"]
            )
    return predictions


def loadAdjudicationDecision(caseId: str) -> dict | None:
    trajectoryPath = TRAJECTORIES_DIR / f"{caseId}_stage3.jsonl"
    if not trajectoryPath.exists():
        return None
    for line in trajectoryPath.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "adjudication_complete":
            return event.get("output", {})
    return None


def formatDiagnosis(result: InvestigationResult) -> str:
    return f"{result.divergence_step}/{result.root_cause_category.value}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze adjudication eval results")
    parser.add_argument("--input", default=str(RESULTS_DIR / "eval_latest.json"))
    args = parser.parse_args()

    inputPath = Path(args.input)
    stage0 = loadPredictions(inputPath, 0)
    stage2 = loadPredictions(inputPath, 2)
    stage3 = loadPredictions(inputPath, 3)

    print(f"Adjudication analysis ({inputPath.name})\n")
    header = (
        f"{'Case':<8} {'S0':>6} {'S2':>6} {'S3':>6} {'Decision':<18} "
        f"{'Final diagnosis':<35} Reason"
    )
    print(header)
    print("-" * len(header))

    s0Scores, s2Scores, s3Scores = [], [], []
    overrides = 0
    successfulOverrides = 0
    harmfulOverrides = 0
    baselinePreserved = 0

    for caseId in BENCHMARK_CASE_IDS:
        if caseId not in stage0 or caseId not in stage3:
            continue
        case = loadCase(CASES_DIR / f"{caseId}.json")
        validIds = getValidLogIds(case)
        s0 = scoreInvestigation(stage0[caseId], case.ground_truth, validIds)
        s2 = scoreInvestigation(stage2[caseId], case.ground_truth, validIds) if caseId in stage2 else None
        s3 = scoreInvestigation(stage3[caseId], case.ground_truth, validIds)
        s0Scores.append(s0)
        if s2:
            s2Scores.append(s2)
        s3Scores.append(s3)

        adj = loadAdjudicationDecision(caseId)
        decision = adj.get("decision", "unknown") if adj else "unknown"
        reason = (adj.get("comparison", {}) or {}).get("why_selected", "") if adj else ""
        if len(reason) > 60:
            reason = reason[:57] + "..."

        if decision == "override_baseline":
            overrides += 1
            if s3.total > s0.total:
                successfulOverrides += 1
            elif s3.total < s0.total:
                harmfulOverrides += 1
        elif decision == "keep_baseline":
            baselinePreserved += 1

        s2Display = f"{s2.total * 100:5.1f}%" if s2 else "  n/a"
        print(
            f"{caseId:<8} {s0.total * 100:5.1f}% {s2Display} {s3.total * 100:5.1f}% "
            f"{decision:<18} {formatDiagnosis(stage3[caseId]):<35} {reason}"
        )

    print("-" * len(header))
    print(
        f"{'MEAN':<8} {investigationQualityScore(s0Scores):5.1f} "
        f"{investigationQualityScore(s2Scores):5.1f} "
        f"{investigationQualityScore(s3Scores):5.1f}"
    )
    overridePrecision = successfulOverrides / overrides if overrides else 0.0
    print(f"\nBaseline preserved: {baselinePreserved}")
    print(f"Overrides: {overrides} (successful={successfulOverrides}, harmful={harmfulOverrides})")
    print(f"Override precision: {overridePrecision:.2f}")
    print(f"Baseline regressions (S3 < S0): {sum(1 for a, b in zip(s0Scores, s3Scores) if b.total < a.total)}")


if __name__ == "__main__":
    main()
