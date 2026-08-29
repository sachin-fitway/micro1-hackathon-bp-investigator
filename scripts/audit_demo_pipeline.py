#!/usr/bin/env python3
"""Run demo cases through the UI API stack and verify diagnosis integrity."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generate_data import buildCases
from shared.llm import GeminiClient
from ui.incident_service import loadCaseFromBenchmark, runIncidentInvestigation

DEMO_CASES = ("case_01", "case_11", "case_14", "case_15")


def verifyCase(caseId: str, client: GeminiClient, live: bool) -> tuple[bool, float]:
    case = loadCaseFromBenchmark(caseId)
    start = time.perf_counter()
    if live:
        result = runIncidentInvestigation(case, client, investigationStage=3)
    else:
        artifactsDir = ROOT / "reports" / "artifacts"
        artifactPath = artifactsDir / f"{caseId}_post_mortem.json"
        if not artifactPath.exists():
            print(f"SKIP {caseId}: no artifact at {artifactPath}")
            return False, 0.0
        from unittest.mock import patch
        from shared.schemas import InvestigationResult

        stored = json.loads(artifactPath.read_text(encoding="utf-8"))
        diagnosis = InvestigationResult.model_validate(stored["diagnosis"])

        class ArtifactClient:
            def completeJson(self, prompt, modelClass, stage="unknown"):
                from agents.post_mortem_reporter import REQUIRED_POST_MORTEM_SECTIONS
                from shared.llm import LlmCallResult
                from shared.schemas import PostMortemReport

                if modelClass.__name__ == "PostMortemReport":
                    md = "\n\n".join(
                        f"## {title}\nUses {diagnosis.culprit_log_ids[0]}."
                        for title in REQUIRED_POST_MORTEM_SECTIONS
                    )
                    return LlmCallResult(
                        parsed=PostMortemReport(markdown=md),
                        raw_response="{}",
                        retry_count=0,
                    )
                raise AssertionError(modelClass)

        with patch("ui.incident_service.runWorkflowFull", return_value=diagnosis):
            result = runIncidentInvestigation(case, ArtifactClient(), investigationStage=3)
    elapsed = time.perf_counter() - start

    sourceIds = {log.log_id for log in case.raw_logs}
    badIds = [
        entry.log_id
        for entry in result.hydrated_logs
        if entry.role in ("culprit", "evidence", "culprit+evidence")
        and entry.log_id not in sourceIds
    ]
    ok = (
        result.diagnosis_integrity_verified
        and not badIds
        and result.diagnosis.divergence_step
        and result.diagnosis.culprit_log_ids
    )
    mode = "LIVE" if live else "MOCK"
    print(
        f"{'OK' if ok else 'FAIL'} [{mode}] {caseId}: "
        f"{result.diagnosis.divergence_step} / {result.diagnosis.root_cause_category.value} "
        f"culprits={result.diagnosis.culprit_log_ids} ({elapsed:.1f}s)"
    )
    if badIds:
        print(f"  ungrounded log IDs in UI: {badIds}")
    return ok, elapsed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Verify UI/API pipeline for demo cases")
    parser.add_argument("--live", action="store_true", help="Run real LLM pipeline (slow)")
    args = parser.parse_args()

    client = GeminiClient() if args.live else None
    failures = 0
    totalTime = 0.0
    for caseId in DEMO_CASES:
        ok, elapsed = verifyCase(caseId, client, args.live)
        totalTime += elapsed
        if not ok:
            failures += 1
    print(f"\nTotal time: {totalTime:.1f}s across {len(DEMO_CASES)} cases")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
