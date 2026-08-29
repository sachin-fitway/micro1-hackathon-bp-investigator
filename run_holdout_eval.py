#!/usr/bin/env python3
"""Evaluate frozen Stage 0 and Stage 3 on unseen holdout cases."""

from __future__ import annotations

import json
from pathlib import Path

from generate_holdout_data import writeHoldoutCases
from run_eval import CaseStageResult, saveResults, runStageOnCases
from shared.case_loader import getValidLogIds
from shared.holdout_loader import HOLDOUT_DIR, loadAllHoldoutCases
from shared.llm import GeminiClient, loadLlmConfig
from shared.scoring import investigationQualityScore, scoreInvestigation
from shared.schemas import InvestigationResult

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEV_SUBMISSION = RESULTS_DIR / "eval_submission.json"
OUTPUT_PATH = RESULTS_DIR / "eval_holdout.json"


def dimMean(scores, fn) -> float:
    return sum(fn(item.score) for item in scores) / len(scores) * 100


def main() -> None:
    if not HOLDOUT_DIR.exists() or not list(HOLDOUT_DIR.glob("case_*.json")):
        writeHoldoutCases(HOLDOUT_DIR)

    cases = loadAllHoldoutCases()
    config = loadLlmConfig()
    client = GeminiClient()

    print(f"Provider: {config.provider} | Model: {config.model} | max_output_tokens: {config.max_output_tokens}")
    print(f"Holdout cases: {len(cases)} | Stages: [0, 3]")
    print("Rubrik: Div 35% | Cause 30% | EvidRec 15% | EvidPrec 10% | NoFab 10%\n")

    stageResults: dict[int, list[CaseStageResult]] = {}

    for stage in (0, 3):
        print(f"=== Stage {stage} ===")
        stageResults[stage] = runStageOnCases(stage, cases, client)

    stageMeans = {
        stage: investigationQualityScore([item.score for item in results])
        for stage, results in stageResults.items()
    }

    saveResults(
        OUTPUT_PATH,
        {
            "provider": config.provider,
            "model": config.model,
            "max_output_tokens": config.max_output_tokens,
            "llm_calls": len(client.auditLog.calls),
            "status": "complete",
            "completed_stages": [0, 3],
            "dataset": "holdout",
            "case_ids": [case.case_id for case in cases],
        },
        stageResults,
        stageMeans,
    )

    s0Map = {item.case_id: item for item in stageResults[0]}
    s3Map = {item.case_id: item for item in stageResults[3]}
    wins = losses = ties = 0
    harmful: list[str] = []

    print("\nPer-case holdout (Stage 0 → Stage 3):")
    for case in cases:
        s0 = s0Map[case.case_id].score.total * 100
        s3 = s3Map[case.case_id].score.total * 100
        delta = s3 - s0
        if s3Map[case.case_id].score.total > s0Map[case.case_id].score.total + 1e-9:
            wins += 1
            tag = "WIN"
        elif s3Map[case.case_id].score.total < s0Map[case.case_id].score.total - 1e-9:
            losses += 1
            tag = "LOSS"
            harmful.append(case.case_id)
        else:
            ties += 1
            tag = "TIE"
        print(f"  {case.case_id}: {s0:5.1f} → {s3:5.1f} ({delta:+5.1f}) [{tag}]")

    print(f"\nHoldout mean IQS — Stage 0: {stageMeans[0]:.2f}% | Stage 3: {stageMeans[3]:.2f}%")
    print(f"Wins / losses / ties: {wins} / {losses} / {ties}")
    if harmful:
        print(f"Harmful regressions: {', '.join(harmful)}")
    else:
        print("Harmful regressions: none")

    print("\nHoldout dimension means (Stage 0 → Stage 3):")
    for label, fn in [
        ("Divergence", lambda s: s.failure_point),
        ("Root cause", lambda s: s.root_cause),
        ("Evidence recall", lambda s: s.evidence_recall),
        ("Evidence precision", lambda s: s.evidence_precision),
        ("No fabrication", lambda s: s.no_fabricated),
    ]:
        print(f"  {label:18s}: {dimMean(stageResults[0], fn):5.1f}% → {dimMean(stageResults[3], fn):5.1f}%")

    if DEV_SUBMISSION.exists():
        dev = json.loads(DEV_SUBMISSION.read_text())
        print("\nComparison vs 15-case development benchmark (eval_submission.json):")
        print(f"  Dev Stage 0:  {dev['stage_means_iqs']['0']:.2f}%")
        print(f"  Dev Stage 3:  {dev['stage_means_iqs']['3']:.2f}%")
        print(f"  Holdout S0:   {stageMeans[0]:.2f}% ({stageMeans[0] - dev['stage_means_iqs']['0']:+.2f} pp vs dev S0)")
        print(f"  Holdout S3:   {stageMeans[3]:.2f}% ({stageMeans[3] - dev['stage_means_iqs']['3']:+.2f} pp vs dev S3)")

    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
