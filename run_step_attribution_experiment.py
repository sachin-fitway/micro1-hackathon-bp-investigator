#!/usr/bin/env python3
"""ARCHIVED / NON-CANONICAL — reverted experiment. Do not use for submission metrics.

One-shot experiment runner: dev + holdout with checkpoint comparison.
Reverted: upstream step hints in baseline dropped dev IQS to ~82.3%.
"""

from __future__ import annotations

import json
from pathlib import Path

from run_eval import CaseStageResult, saveResults, runStageOnCases
from shared.case_loader import getValidLogIds, loadAllCases
from shared.holdout_loader import loadAllHoldoutCases
from shared.llm import GeminiClient, loadLlmConfig
from shared.scoring import investigationQualityScore, scoreInvestigation

RESULTS_DIR = Path(__file__).resolve().parent / "results"
OUTPUT_PATH = RESULTS_DIR / "eval_step_attribution_experiment.json"
FROZEN_DEV = RESULTS_DIR / "eval_submission.json"
FROZEN_HOLDOUT = RESULTS_DIR / "eval_holdout.json"


def loadFrozenCases(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases", {})


def dimMean(results: list[CaseStageResult], fn) -> float:
    return sum(fn(item.score) for item in results) / len(results) * 100


def divergenceAccuracy(results: list[CaseStageResult], cases) -> float:
    truthMap = {case.case_id: case.ground_truth.divergence_step for case in cases}
    correct = sum(
        1
        for item in results
        if item.prediction.divergence_step.strip().lower()
        == truthMap[item.case_id].strip().lower()
    )
    return correct / len(results) * 100


def rootCauseAccuracy(results: list[CaseStageResult], cases) -> float:
    truthMap = {case.case_id: case.ground_truth.root_cause_category for case in cases}
    correct = sum(
        1
        for item in results
        if item.prediction.root_cause_category == truthMap[item.case_id]
    )
    return correct / len(results) * 100


def summarizeDataset(
    label: str,
    cases,
    stageResults: dict[int, list[CaseStageResult]],
    frozenCases: dict[str, dict],
) -> dict:
    summary: dict = {"label": label, "stages": {}}
    for stage in (0, 3):
        results = stageResults[stage]
        summary["stages"][str(stage)] = {
            "mean_iqs": investigationQualityScore([item.score for item in results]),
            "divergence_accuracy": divergenceAccuracy(results, cases),
            "root_cause_accuracy": rootCauseAccuracy(results, cases),
            "evidence_recall": dimMean(results, lambda s: s.evidence_recall),
            "evidence_precision": dimMean(results, lambda s: s.evidence_precision),
            "no_fabrication": dimMean(results, lambda s: s.no_fabricated),
        }

    perCase: dict[str, dict] = {}
    s0Map = {item.case_id: item for item in stageResults[0]}
    s3Map = {item.case_id: item for item in stageResults[3]}
    regressions: list[str] = []

    for case in cases:
        caseId = case.case_id
        expS0 = s0Map[caseId].score.total * 100
        expS3 = s3Map[caseId].score.total * 100
        frozenS0 = frozenCases.get(caseId, {}).get("stage_0", {}).get("iqs")
        frozenS3 = frozenCases.get(caseId, {}).get("stage_3", {}).get("iqs")
        deltaS0 = expS0 - frozenS0 if frozenS0 is not None else None
        deltaS3 = expS3 - frozenS3 if frozenS3 is not None else None
        if frozenS0 is not None and expS0 < frozenS0 - 1e-9:
            regressions.append(f"{caseId}:stage_0")
        if frozenS3 is not None and expS3 < frozenS3 - 1e-9:
            regressions.append(f"{caseId}:stage_3")

        perCase[caseId] = {
            "frozen_stage_0_iqs": frozenS0,
            "experiment_stage_0_iqs": expS0,
            "delta_stage_0": deltaS0,
            "frozen_stage_3_iqs": frozenS3,
            "experiment_stage_3_iqs": expS3,
            "delta_stage_3": deltaS3,
            "stage_0": {
                "iqs": expS0,
                "score_breakdown": s0Map[caseId].score.model_dump(),
                "prediction": s0Map[caseId].prediction.model_dump(mode="json"),
            },
            "stage_3": {
                "iqs": expS3,
                "score_breakdown": s3Map[caseId].score.model_dump(),
                "prediction": s3Map[caseId].prediction.model_dump(mode="json"),
            },
        }

    summary["per_case"] = perCase
    summary["regressions_vs_frozen"] = regressions
    return summary


def main() -> None:
    config = loadLlmConfig()
    client = GeminiClient()
    devCases = loadAllCases()
    holdoutCases = loadAllHoldoutCases()

    print("=== Step Attribution Experiment ===")
    print(f"Model: {config.model}\n")

    allStageResults: dict[str, dict[int, list[CaseStageResult]]] = {}

    for label, cases in (("development", devCases), ("holdout", holdoutCases)):
        print(f"--- {label} ({len(cases)} cases) ---")
        stageResults: dict[int, list[CaseStageResult]] = {}
        for stage in (0, 3):
            print(f"  Stage {stage} ...")
            stageResults[stage] = runStageOnCases(stage, cases, client)
        allStageResults[label] = stageResults

    frozenDev = loadFrozenCases(FROZEN_DEV)
    frozenHoldout = loadFrozenCases(FROZEN_HOLDOUT)

    devSummary = summarizeDataset(
        "development", devCases, allStageResults["development"], frozenDev
    )
    holdoutSummary = summarizeDataset(
        "holdout", holdoutCases, allStageResults["holdout"], frozenHoldout
    )

    combinedCases: dict = {}
    for caseId, entry in devSummary["per_case"].items():
        combinedCases[caseId] = entry
    for caseId, entry in holdoutSummary["per_case"].items():
        combinedCases[caseId] = entry

    payload = {
        "config": {
            "experiment": "step_attribution_origin_vs_enforcement",
            "provider": config.provider,
            "model": config.model,
            "max_output_tokens": config.max_output_tokens,
            "llm_calls": len(client.auditLog.calls),
            "status": "complete",
            "frozen_checkpoints": {
                "development": str(FROZEN_DEV),
                "holdout": str(FROZEN_HOLDOUT),
            },
        },
        "development": devSummary,
        "holdout": holdoutSummary,
        "cases": combinedCases,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved {OUTPUT_PATH}")

    print("\n=== Development ===")
    for stage in ("0", "3"):
        s = devSummary["stages"][stage]
        print(
            f"  Stage {stage}: IQS={s['mean_iqs']:.2f}% "
            f"div={s['divergence_accuracy']:.1f}% "
            f"cause={s['root_cause_accuracy']:.1f}%"
        )
    if devSummary["regressions_vs_frozen"]:
        print(f"  Regressions: {devSummary['regressions_vs_frozen']}")

    print("\n=== Holdout ===")
    for stage in ("0", "3"):
        s = holdoutSummary["stages"][stage]
        print(
            f"  Stage {stage}: IQS={s['mean_iqs']:.2f}% "
            f"div={s['divergence_accuracy']:.1f}% "
            f"cause={s['root_cause_accuracy']:.1f}%"
        )
    if holdoutSummary["regressions_vs_frozen"]:
        print(f"  Regressions: {holdoutSummary['regressions_vs_frozen']}")


if __name__ == "__main__":
    main()
