#!/usr/bin/env python3
"""End-to-end incident flow: raw logs → investigation → evidence hydration → post-mortem."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agents.log_lookup import LogLookupTool
from agents.post_mortem_reporter import (
    hydrateDiagnosisLogs,
    runPostMortemReporter,
)
from shared.case_loader import CASES_DIR, loadCase
from shared.llm import GeminiClient, loadLlmConfig
from shared.schemas import EvalCase, InvestigationResult, PostMortemArtifact
from shared.trajectories import TrajectoryLogger
from workflows.ablation import STAGE_LABELS, STAGE_RUNNERS

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "reports" / "artifacts"


@dataclass
class InvestigationPhaseResult:
    case_id: str
    stage: int
    diagnosis: InvestigationResult
    trajectory_path: Path | None


@dataclass
class IncidentFlowResult:
    case_id: str
    investigation: InvestigationPhaseResult
    post_mortem: PostMortemArtifact
    report_path: Path
    artifact_path: Path


def printPhaseBanner(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def printRawLogsSummary(case: EvalCase) -> None:
    printPhaseBanner("PHASE 1 — Raw Logs Ingested")
    print(f"  Process:     {case.process_context.process_name}")
    print(f"  Sequence:    {' → '.join(case.process_context.expected_sequence)}")
    print(f"  Log count:   {len(case.raw_logs)}")
    correlationIds = {
        log.metadata.get("correlation_id", "—")
        for log in case.raw_logs
        if not log.metadata.get("irrelevant")
    }
    print(f"  Correlation: {', '.join(sorted(correlationIds))}")
    print("\n  Sample timeline (non-noise logs):")
    for log in sorted(
        (entry for entry in case.raw_logs if not entry.metadata.get("irrelevant")),
        key=lambda entry: entry.timestamp,
    )[:6]:
        print(f"    [{log.timestamp}] {log.log_id} {log.service}: {log.message[:70]}")


def runInvestigationPhase(
    case: EvalCase,
    client: GeminiClient,
    stage: int,
) -> InvestigationPhaseResult:
    printPhaseBanner(f"PHASE 2 — Investigation ({STAGE_LABELS[stage]})")
    trajectory = TrajectoryLogger(case.case_id, stage=str(stage))
    runner = STAGE_RUNNERS[stage]
    diagnosis = runner(case, client)
    print(f"  Divergence step:     {diagnosis.divergence_step}")
    print(f"  Root cause category: {diagnosis.root_cause_category.value}")
    print(f"  Culprit logs:        {', '.join(diagnosis.culprit_log_ids)}")
    print(f"  Evidence logs:       {', '.join(diagnosis.evidence_log_ids)}")
    print(f"  Trajectory:          {trajectory.file_path}")
    return InvestigationPhaseResult(
        case_id=case.case_id,
        stage=stage,
        diagnosis=diagnosis,
        trajectory_path=trajectory.file_path,
    )


def printEvidenceHydration(case: EvalCase, diagnosis: InvestigationResult) -> None:
    printPhaseBanner("PHASE 3 — Evidence Hydration (fetch_log_details)")
    evidenceLogs, culpritLogs, unknown = hydrateDiagnosisLogs(case, diagnosis)
    hydrated = dict(evidenceLogs)
    hydrated.update(culpritLogs)
    print(f"  Evidence logs retrieved: {len(evidenceLogs)}")
    print(f"  Culprit logs retrieved:  {len(culpritLogs)}")
    if unknown:
        print(f"  Unknown log IDs:           {', '.join(unknown)}")
    for logId in list(dict.fromkeys(diagnosis.evidence_log_ids + diagnosis.culprit_log_ids)):
        if logId not in hydrated:
            print(f"    ✗ {logId} — not found")
            continue
        log = hydrated[logId]
        print(f"    ✓ {logId} [{log.timestamp}] {log.service}: {log.message[:60]}")


def runPostMortemPhase(
    case: EvalCase,
    diagnosis: InvestigationResult,
    client: GeminiClient,
    investigationStage: int,
) -> PostMortemArtifact:
    printPhaseBanner("PHASE 4 — Post-Mortem Report Generation")
    trajectory = TrajectoryLogger(case.case_id, stage="post_mortem")
    artifact = runPostMortemReporter(
        case,
        diagnosis,
        client,
        trajectory=trajectory,
        investigationStage=investigationStage,
    )
    print(f"  Report sections:   {len([line for line in artifact.markdown.splitlines() if line.startswith('## ')])}")
    print(f"  Claim traces:      {len(artifact.claim_traces)}")
    print(f"  Diagnosis preserved: {artifact.diagnosis.divergence_step} / "
          f"{artifact.diagnosis.root_cause_category.value}")
    print(f"  Trajectory:        {trajectory.file_path}")
    return artifact


def runIncidentFlow(
    case: EvalCase,
    client: GeminiClient,
    investigationStage: int = 3,
    outputDir: Path = REPORTS_DIR,
) -> IncidentFlowResult:
    outputDir.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    printPhaseBanner(f"INCIDENT INVESTIGATION → POST-MORTEM  ({case.case_id})")
    printRawLogsSummary(case)

    investigation = runInvestigationPhase(case, client, investigationStage)
    printEvidenceHydration(case, investigation.diagnosis)

    artifact = runPostMortemPhase(
        case,
        investigation.diagnosis,
        client,
        investigationStage,
    )

    reportPath = outputDir / f"{case.case_id}_post_mortem.md"
    artifactPath = ARTIFACTS_DIR / f"{case.case_id}_post_mortem.json"
    reportPath.write_text(artifact.markdown, encoding="utf-8")
    artifactPath.write_text(
        json.dumps(
            {
                "case_id": artifact.case_id,
                "investigation_stage": artifact.investigation_stage,
                "diagnosis": artifact.diagnosis.model_dump(mode="json"),
                "retrieved_evidence_log_ids": artifact.retrieved_evidence_log_ids,
                "retrieved_culprit_log_ids": artifact.retrieved_culprit_log_ids,
                "unknown_log_ids": artifact.unknown_log_ids,
                "claim_traces": [trace.model_dump(mode="json") for trace in artifact.claim_traces],
                "evidence_table_markdown": artifact.evidence_table_markdown,
                "report_path": str(reportPath),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    printPhaseBanner("PHASE 5 — Deliverables")
    print(f"  Markdown report:  {reportPath}")
    print(f"  JSON artifact:    {artifactPath}")
    print("\n  Evidence trace preview:")
    for trace in artifact.claim_traces[:4]:
        logs = ", ".join(trace.supporting_log_ids)
        print(f"    • {trace.claim[:72]}…" if len(trace.claim) > 72 else f"    • {trace.claim}")
        print(f"      → logs: {logs}")
    if len(artifact.claim_traces) > 4:
        print(f"    … and {len(artifact.claim_traces) - 4} more claims")

    return IncidentFlowResult(
        case_id=case.case_id,
        investigation=investigation,
        post_mortem=artifact,
        report_path=reportPath,
        artifact_path=artifactPath,
    )


def loadFrozenDiagnosis(caseId: str, resultsPath: Path, stage: int = 3) -> InvestigationResult:
    payload = json.loads(resultsPath.read_text(encoding="utf-8"))
    entry = payload["cases"][caseId][f"stage_{stage}"]
    return InvestigationResult.model_validate(entry["prediction"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end incident investigation → post-mortem product flow",
    )
    parser.add_argument("--case", default="", help="Single case ID (e.g. case_01)")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs")
    parser.add_argument(
        "--stage",
        type=int,
        default=3,
        choices=[0, 1, 2, 3],
        help="Investigation stage (default: 3 = full workflow)",
    )
    parser.add_argument(
        "--from-frozen",
        action="store_true",
        help="Skip investigation; load diagnosis from frozen eval results",
    )
    parser.add_argument(
        "--results",
        default=str(RESULTS_DIR / "eval_submission.json"),
        help="Frozen results JSON when using --from-frozen",
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
        caseIds = ["case_01"]

    config = loadLlmConfig()
    client = GeminiClient()
    outputDir = Path(args.output_dir)
    resultsPath = Path(args.results)

    print(f"Provider: {config.provider} | Model: {config.model}")

    for caseId in caseIds:
        case = loadCase(CASES_DIR / f"{caseId}.json")
        if args.from_frozen:
            printPhaseBanner(f"INCIDENT POST-MORTEM (frozen diagnosis) — {caseId}")
            printRawLogsSummary(case)
            diagnosis = loadFrozenDiagnosis(caseId, resultsPath, stage=args.stage)
            printPhaseBanner(f"PHASE 2 — Frozen Diagnosis (stage {args.stage})")
            print(f"  Divergence step:     {diagnosis.divergence_step}")
            print(f"  Root cause category: {diagnosis.root_cause_category.value}")
            printEvidenceHydration(case, diagnosis)
            artifact = runPostMortemPhase(case, diagnosis, client, args.stage)
            reportPath = outputDir / f"{caseId}_post_mortem.md"
            artifactPath = ARTIFACTS_DIR / f"{caseId}_post_mortem.json"
            reportPath.write_text(artifact.markdown, encoding="utf-8")
            artifactPath.write_text(
                json.dumps(
                    {
                        "case_id": artifact.case_id,
                        "diagnosis": artifact.diagnosis.model_dump(mode="json"),
                        "claim_traces": [t.model_dump(mode="json") for t in artifact.claim_traces],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"\nWrote {reportPath}")
        else:
            runIncidentFlow(case, client, investigationStage=args.stage, outputDir=outputDir)


if __name__ == "__main__":
    main()
