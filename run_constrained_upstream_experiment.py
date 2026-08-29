#!/usr/bin/env python3
"""ARCHIVED / NON-CANONICAL — reverted experiment. Do not use for submission metrics.

Constrained upstream challenger experiment — frozen S0, experimental S3 only.
Reverted: harmful overrides on case_03, case_11.
"""

from __future__ import annotations

import json
from pathlib import Path

from run_eval import CaseStageResult
from shared.case_loader import getValidLogIds, loadAllCases
from shared.holdout_loader import loadAllHoldoutCases
from shared.llm import GeminiClient, loadLlmConfig
from shared.scoring import investigationQualityScore, scoreInvestigation
from shared.schemas import InvestigationResult, ScoreBreakdown
from workflows.ablation import runStage3WorkflowFull

RESULTS_DIR = Path(__file__).resolve().parent / "results"
TRAJECTORIES_DIR = Path(__file__).resolve().parent / "trajectories"
OUTPUT_PATH = RESULTS_DIR / "eval_constrained_upstream_experiment.json"
FROZEN_DEV = RESULTS_DIR / "eval_submission.json"
FROZEN_HOLDOUT = RESULTS_DIR / "eval_holdout.json"


def loadFrozenStage(path: Path, stage: int) -> dict[str, CaseStageResult]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results: dict[str, CaseStageResult] = {}
    for caseId, stageEntries in payload.get("cases", {}).items():
        key = f"stage_{stage}"
        if key not in stageEntries:
            continue
        entry = stageEntries[key]
        results[caseId] = CaseStageResult(
            case_id=caseId,
            stage=stage,
            score=ScoreBreakdown.model_validate(entry["score_breakdown"]),
            prediction=InvestigationResult.model_validate(entry["prediction"]),
        )
    return results


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


def parseTrajectoryMetrics(caseId: str) -> dict:
    path = TRAJECTORIES_DIR / f"{caseId}_stage3.jsonl"
    metrics = {
        "no_challenge": False,
        "upstream_proposal": False,
        "override": False,
        "keep_baseline": False,
    }
    if not path.exists():
        return metrics
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event = record.get("event", "")
        if event == "challenger_no_challenge":
            metrics["no_challenge"] = True
        if event == "challenger_upstream_proposal":
            metrics["upstream_proposal"] = True
        if event == "adjudication_override_baseline":
            metrics["override"] = True
        if event == "adjudication_keep_baseline":
            metrics["keep_baseline"] = True
    return metrics


def runExperimentalStage3(cases, client: GeminiClient) -> list[CaseStageResult]:
    results: list[CaseStageResult] = []
    for case in cases:
        print(f"  [Stage 3 experiment] {case.case_id} ...", flush=True)
        trajPath = TRAJECTORIES_DIR / f"{case.case_id}_stage3.jsonl"
        if trajPath.exists():
            trajPath.unlink()
        prediction = runStage3WorkflowFull(case, client)
        score = scoreInvestigation(prediction, case.ground_truth, getValidLogIds(case))
        results.append(
            CaseStageResult(
                case_id=case.case_id,
                stage=3,
                score=score,
                prediction=prediction,
            )
        )
    return results


def summarizeDataset(
    label: str,
    cases,
    frozenS0: dict[str, CaseStageResult],
    frozenS3: dict[str, CaseStageResult],
    expS3: list[CaseStageResult],
) -> dict:
    expS3Map = {item.case_id: item for item in expS3}
    frozenS0List = [frozenS0[case.case_id] for case in cases if case.case_id in frozenS0]
    frozenS3List = [frozenS3[case.case_id] for case in cases if case.case_id in frozenS3]

    summary = {
        "label": label,
        "frozen_stage_0": {
            "mean_iqs": investigationQualityScore([item.score for item in frozenS0List]),
            "divergence_accuracy": divergenceAccuracy(frozenS0List, cases),
            "root_cause_accuracy": rootCauseAccuracy(frozenS0List, cases),
            "evidence_recall": dimMean(frozenS0List, lambda s: s.evidence_recall),
            "evidence_precision": dimMean(frozenS0List, lambda s: s.evidence_precision),
            "no_fabrication": dimMean(frozenS0List, lambda s: s.no_fabricated),
        },
        "frozen_stage_3": {
            "mean_iqs": investigationQualityScore([item.score for item in frozenS3List]),
            "divergence_accuracy": divergenceAccuracy(frozenS3List, cases),
            "root_cause_accuracy": rootCauseAccuracy(frozenS3List, cases),
            "evidence_recall": dimMean(frozenS3List, lambda s: s.evidence_recall),
            "evidence_precision": dimMean(frozenS3List, lambda s: s.evidence_precision),
            "no_fabrication": dimMean(frozenS3List, lambda s: s.no_fabricated),
        },
        "experiment_stage_3": {
            "mean_iqs": investigationQualityScore([item.score for item in expS3]),
            "divergence_accuracy": divergenceAccuracy(expS3, cases),
            "root_cause_accuracy": rootCauseAccuracy(expS3, cases),
            "evidence_recall": dimMean(expS3, lambda s: s.evidence_recall),
            "evidence_precision": dimMean(expS3, lambda s: s.evidence_precision),
            "no_fabrication": dimMean(expS3, lambda s: s.no_fabricated),
        },
    }

    wins = losses = ties = 0
    regressions: list[str] = []
    perCase: dict = {}
    noChallenge = upstreamProposal = overrides = harmfulOverrides = goodOverrides = 0

    for case in cases:
        caseId = case.case_id
        frozen0 = frozenS0[caseId].score.total * 100
        frozen3 = frozenS3[caseId].score.total * 100
        exp3 = expS3Map[caseId].score.total * 100
        deltaVsFrozenS3 = exp3 - frozen3
        deltaS3vsS0 = exp3 - frozen0

        if exp3 > frozen3 + 1e-9:
            wins += 1
        elif exp3 < frozen3 - 1e-9:
            losses += 1
            regressions.append(caseId)
        else:
            ties += 1

        traj = parseTrajectoryMetrics(caseId)
        if traj["no_challenge"]:
            noChallenge += 1
        if traj["upstream_proposal"]:
            upstreamProposal += 1
        if traj["override"]:
            overrides += 1
            if exp3 > frozen3 + 1e-9:
                goodOverrides += 1
            elif exp3 < frozen3 - 1e-9:
                harmfulOverrides += 1

        perCase[caseId] = {
            "frozen_stage_0_iqs": frozen0,
            "frozen_stage_3_iqs": frozen3,
            "experiment_stage_3_iqs": exp3,
            "delta_vs_frozen_stage_3": deltaVsFrozenS3,
            "delta_stage_3_vs_frozen_stage_0": deltaS3vsS0,
            "trajectory": traj,
            "stage_3": {
                "iqs": exp3,
                "score_breakdown": expS3Map[caseId].score.model_dump(),
                "prediction": expS3Map[caseId].prediction.model_dump(mode="json"),
            },
        }

    overridePrecision = goodOverrides / overrides * 100 if overrides else 100.0
    summary["wins_losses_ties"] = {"wins": wins, "losses": losses, "ties": ties}
    summary["regressions_vs_frozen_stage_3"] = regressions
    summary["adjudication_metrics"] = {
        "no_challenge_count": noChallenge,
        "upstream_proposal_count": upstreamProposal,
        "override_count": overrides,
        "good_override_count": goodOverrides,
        "harmful_override_count": harmfulOverrides,
        "override_precision_pct": overridePrecision,
        "no_challenge_rate_pct": noChallenge / len(cases) * 100,
    }
    summary["per_case"] = perCase
    return summary


def main() -> None:
    config = loadLlmConfig()
    client = GeminiClient()
    devCases = loadAllCases()
    holdoutCases = loadAllHoldoutCases()

    frozenDevS0 = loadFrozenStage(FROZEN_DEV, 0)
    frozenDevS3 = loadFrozenStage(FROZEN_DEV, 3)
    frozenHoldoutS0 = loadFrozenStage(FROZEN_HOLDOUT, 0)
    frozenHoldoutS3 = loadFrozenStage(FROZEN_HOLDOUT, 3)

    print("=== Constrained Upstream Challenger Experiment ===")
    print(f"Model: {config.model}\n")

    print(f"--- Development S3 ({len(devCases)} cases) ---")
    devExpS3 = runExperimentalStage3(devCases, client)

    print(f"\n--- Holdout S3 ({len(holdoutCases)} cases) ---")
    holdoutExpS3 = runExperimentalStage3(holdoutCases, client)

    devSummary = summarizeDataset(
        "development", devCases, frozenDevS0, frozenDevS3, devExpS3
    )
    holdoutSummary = summarizeDataset(
        "holdout", holdoutCases, frozenHoldoutS0, frozenHoldoutS3, holdoutExpS3
    )

    payload = {
        "config": {
            "experiment": "constrained_upstream_challenger",
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
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
