#!/usr/bin/env python3
"""Run baseline and ablation evaluation across all benchmark cases."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from generate_data import writeCases
from shared.case_loader import CASES_DIR, getValidLogIds, loadAllCases
from shared.llm import GeminiClient, LlmAuditLog, loadLlmConfig
from shared.scoring import investigationQualityScore, scoreInvestigation
from shared.schemas import EvalCase, InvestigationResult, ScoreBreakdown
from workflows.ablation import STAGE_LABELS, STAGE_RUNNERS

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class CaseStageResult:
    case_id: str
    stage: int
    score: ScoreBreakdown
    prediction: InvestigationResult


def ensureCasesExist() -> None:
    if not CASES_DIR.exists() or not list(CASES_DIR.glob("case_*.json")):
        writeCases(CASES_DIR)


def runStageOnCases(
    stage: int,
    cases: list[EvalCase],
    client: GeminiClient,
    existingResults: list[CaseStageResult] | None = None,
    onCaseComplete: Callable[[int, list[CaseStageResult]], None] | None = None,
) -> list[CaseStageResult]:
    runner = STAGE_RUNNERS[stage]
    completed = {item.case_id: item for item in (existingResults or [])}
    results: list[CaseStageResult] = list(completed.values())
    for case in cases:
        if case.case_id in completed:
            print(f"  [{STAGE_LABELS[stage]}] {case.case_id} ... skipped (checkpoint)", flush=True)
            continue
        print(f"  [{STAGE_LABELS[stage]}] {case.case_id} ...", flush=True)
        prediction = runner(case, client)
        score = scoreInvestigation(prediction, case.ground_truth, getValidLogIds(case))
        result = CaseStageResult(
            case_id=case.case_id,
            stage=stage,
            score=score,
            prediction=prediction,
        )
        results.append(result)
        completed[case.case_id] = result
        if onCaseComplete:
            onCaseComplete(stage, results)
    return results


def formatScore(value: float) -> str:
    return f"{value * 100:.1f}%"


def printAblationTable(stageScores: dict[int, float]) -> None:
    print("\nInvestigation Quality Score (IQS) by Stage")
    print("+------+----------------------------------------+--------+")
    print("| Stage| Description                            | IQS    |")
    print("+------+----------------------------------------+--------+")
    for stage in sorted(stageScores):
        print(f"|  {stage}   | {STAGE_LABELS[stage]:<38} | {stageScores[stage]:6.1f} |")
    print("+------+----------------------------------------+--------+")


def printCaseComparisonTable(
    cases: list[EvalCase],
    stageResults: dict[int, list[CaseStageResult]],
) -> None:
    print("\nPer-Case Scores (Stage 0 vs Stage 3)")
    print("+--------+------------------+--------+--------+")
    print("| Case   | Pattern          | Stg 0  | Stg 3  |")
    print("+--------+------------------+--------+--------+")
    stage0Map = {item.case_id: item for item in stageResults.get(0, [])}
    stage3Map = {item.case_id: item for item in stageResults.get(3, [])}
    for case in cases:
        s0 = stage0Map.get(case.case_id)
        s3 = stage3Map.get(case.case_id)
        stg0 = formatScore(s0.score.total) if s0 else "N/A"
        stg3 = formatScore(s3.score.total) if s3 else "N/A"
        print(f"| {case.case_id:<6} | {case.meta.failure_pattern:<16} | {stg0:>6} | {stg3:>6} |")
    print("+--------+------------------+--------+--------+")


def printBaselineFailureAnalysis(cases: list[EvalCase], stage0: list[CaseStageResult]) -> None:
    print("\nStage 0 Baseline Failure Analysis (ground truth vs prediction)")
    scoreMap = {item.case_id: item for item in stage0}
    for case in cases:
        item = scoreMap[case.case_id]
        if item.score.total >= 0.99:
            continue
        truth = case.ground_truth
        pred = item.prediction
        print(f"\n  {case.case_id} (IQS={item.score.total * 100:.1f}%)")
        print(f"    Truth step/category: {truth.divergence_step} / {truth.root_cause_category.value}")
        print(f"    Pred  step/category: {pred.divergence_step} / {pred.root_cause_category.value}")
        print(f"    Score dims: div={item.score.failure_point:.0f} cause={item.score.root_cause:.0f} "
              f"rec={item.score.evidence_recall:.2f} prec={item.score.evidence_precision:.2f} "
              f"nofab={item.score.no_fabricated:.0f}")


def printHypothesisCheck(cases: list[EvalCase], stage0: list[CaseStageResult], stage3: list[CaseStageResult]) -> None:
    print("\nPost-hoc baseline_hypothesis check (analysis only, not used in scoring)")
    s0 = {item.case_id: item.score.total for item in stage0}
    s3 = {item.case_id: item.score.total for item in stage3}
    for case in cases:
        winner = "baseline" if s0[case.case_id] > s3[case.case_id] else "agent" if s3[case.case_id] > s0[case.case_id] else "tie"
        if case.meta.baseline_hypothesis != "either" and winner != case.meta.baseline_hypothesis and winner != "tie":
            print(
                f"  {case.case_id}: hypothesis={case.meta.baseline_hypothesis}, "
                f"actual={winner} (stage0={s0[case.case_id]*100:.1f}%, stage3={s3[case.case_id]*100:.1f}%)"
            )


def loadCheckpoint(outputPath: Path) -> dict[int, list[CaseStageResult]]:
    if not outputPath.exists():
        return {}
    payload = json.loads(outputPath.read_text(encoding="utf-8"))
    stageResults: dict[int, list[CaseStageResult]] = {}
    for caseId, stageEntries in payload.get("cases", {}).items():
        for stageKey, entry in stageEntries.items():
            stage = int(stageKey.removeprefix("stage_"))
            stageResults.setdefault(stage, []).append(
                CaseStageResult(
                    case_id=caseId,
                    stage=stage,
                    score=ScoreBreakdown.model_validate(entry["score_breakdown"]),
                    prediction=InvestigationResult.model_validate(entry["prediction"]),
                )
            )
    return stageResults


def mergeStageResults(
    base: dict[int, list[CaseStageResult]],
    updates: dict[int, list[CaseStageResult]],
) -> dict[int, list[CaseStageResult]]:
    merged = {stage: list(results) for stage, results in base.items()}
    for stage, results in updates.items():
        byCase = {item.case_id: item for item in merged.get(stage, [])}
        for item in results:
            byCase[item.case_id] = item
        merged[stage] = list(byCase.values())
    return merged


def saveResults(
    outputPath: Path,
    config: dict,
    stageResults: dict[int, list[CaseStageResult]],
    stageMeans: dict[int, float],
) -> None:
    payload = {
        "config": config,
        "stage_means_iqs": stageMeans,
        "cases": {},
    }
    for stage, results in stageResults.items():
        for item in results:
            payload["cases"].setdefault(item.case_id, {})[f"stage_{stage}"] = {
                "iqs": item.score.total * 100,
                "score_breakdown": item.score.model_dump(),
                "prediction": item.prediction.model_dump(mode="json"),
            }
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parseStages(raw: str) -> list[int]:
    if raw == "all":
        return [0, 1, 2, 3]
    return [int(part.strip()) for part in raw.split(",")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline and ablation stages")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs (default: all)")
    parser.add_argument("--stage", default="all", help="Stage number, comma list, or 'all'")
    parser.add_argument("--post-analysis", action="store_true", help="Print baseline_hypothesis check")
    parser.add_argument("--resume", action="store_true", help="Resume from results/eval_latest.json checkpoint")
    args = parser.parse_args()

    ensureCasesExist()
    cases = loadAllCases()
    if args.cases:
        selected = {part.strip() for part in args.cases.split(",")}
        cases = [case for case in cases if case.case_id in selected]

    stages = parseStages(args.stage)
    config = loadLlmConfig()
    client = GeminiClient()
    auditLog = client.auditLog

    print(f"Provider: {config.provider} | Model: {config.model} | max_output_tokens: {config.max_output_tokens}")
    print(f"Cases: {len(cases)} | Stages: {stages}")
    print("Rubrik: Div 35% | Cause 30% | EvidRec 15% | EvidPrec 10% | NoFab 10%\n")

    outputPath = RESULTS_DIR / "eval_latest.json"
    stageResults: dict[int, list[CaseStageResult]] = loadCheckpoint(outputPath) if args.resume else {}

    def persistProgress(status: str) -> None:
        stageMeansPartial = {
            completedStage: investigationQualityScore([item.score for item in results])
            for completedStage, results in stageResults.items()
        }
        saveResults(
            outputPath,
            {
                "provider": config.provider,
                "model": config.model,
                "max_output_tokens": config.max_output_tokens,
                "llm_calls": len(auditLog.calls),
                "status": status,
                "completed_stages": sorted(stageResults.keys()),
            },
            stageResults,
            stageMeansPartial,
        )

    def onCaseComplete(completedStage: int, results: list[CaseStageResult]) -> None:
        stageResults[completedStage] = results
        persistProgress("in_progress")

    for stage in sorted(stages):
        print(f"=== Stage {stage}: {STAGE_LABELS[stage]} ===")
        stageResults[stage] = runStageOnCases(
            stage,
            cases,
            client,
            existingResults=stageResults.get(stage, []),
            onCaseComplete=onCaseComplete,
        )
        persistProgress("in_progress")

    stageMeans = {
        stage: investigationQualityScore([item.score for item in results])
        for stage, results in stageResults.items()
    }
    printAblationTable(stageMeans)

    if 0 in stageResults and 3 in stageResults:
        printCaseComparisonTable(cases, stageResults)
        printBaselineFailureAnalysis(cases, stageResults[0])
        if args.post_analysis:
            printHypothesisCheck(cases, stageResults[0], stageResults[3])

    outputPath = RESULTS_DIR / "eval_latest.json"
    persistProgress("complete")
    print(f"\nResults saved to {outputPath}")
    print(f"Trajectories saved under trajectories/")


if __name__ == "__main__":
    main()
