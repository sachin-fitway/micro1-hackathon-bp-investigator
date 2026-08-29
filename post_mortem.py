#!/usr/bin/env python3
"""Generate evidence-grounded post-mortem reports from frozen baseline diagnoses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.post_mortem_reporter import runPostMortemReporter
from shared.case_loader import CASES_DIR, loadCase
from shared.llm import GeminiClient
from shared.schemas import InvestigationResult
from shared.trajectories import TrajectoryLogger

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def loadFrozenDiagnosis(caseId: str, resultsPath: Path) -> InvestigationResult:
    payload = json.loads(resultsPath.read_text(encoding="utf-8"))
    if caseId not in payload.get("cases", {}):
        raise KeyError(f"Case {caseId} not found in {resultsPath}")
    entry = payload["cases"][caseId].get("stage_0")
    if not entry:
        raise KeyError(f"No stage_0 prediction for {caseId} in {resultsPath}")
    return InvestigationResult.model_validate(entry["prediction"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate post-mortem reports from frozen baseline")
    parser.add_argument("--case", default="", help="Single case ID (e.g. case_01)")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs")
    parser.add_argument(
        "--from-frozen",
        action="store_true",
        help="Load diagnosis from results/eval_stage0_experiment.json",
    )
    parser.add_argument(
        "--results",
        default=str(RESULTS_DIR / "eval_stage0_experiment.json"),
        help="Frozen baseline results JSON",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPORTS_DIR),
        help="Directory for Markdown reports",
    )
    args = parser.parse_args()

    if args.case:
        caseIds = [args.case.strip()]
    elif args.cases:
        caseIds = [part.strip() for part in args.cases.split(",") if part.strip()]
    else:
        caseIds = ["case_01", "case_03"]

    outputDir = Path(args.output_dir)
    outputDir.mkdir(parents=True, exist_ok=True)
    resultsPath = Path(args.results)
    client = GeminiClient()

    for caseId in caseIds:
        case = loadCase(CASES_DIR / f"{caseId}.json")
        if args.from_frozen or resultsPath.exists():
            diagnosis = loadFrozenDiagnosis(caseId, resultsPath)
        else:
            raise SystemExit(f"No frozen diagnosis available for {caseId}. Pass --from-frozen.")

        trajectory = TrajectoryLogger(caseId, stage="post_mortem")
        artifact = runPostMortemReporter(case, diagnosis, client, trajectory)
        reportPath = outputDir / f"{caseId}_post_mortem.md"
        reportPath.write_text(artifact.markdown, encoding="utf-8")
        print(f"Wrote {reportPath}")
        print(f"  Diagnosis preserved: {artifact.diagnosis.divergence_step} / "
              f"{artifact.diagnosis.root_cause_category.value}")
        print(f"  Evidence logs retrieved: {artifact.retrieved_evidence_log_ids}")
        print(f"  Trajectory: {trajectory.file_path}")


if __name__ == "__main__":
    main()
