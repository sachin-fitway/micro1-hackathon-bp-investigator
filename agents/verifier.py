"""Verifier agent — groundedness checks with deterministic gates."""

from __future__ import annotations

import json

from shared.llm import GeminiClient, LlmCallResult
from shared.prompts import VERIFIER_INSTRUCTIONS
from shared.schemas import EvalCase, InvestigationResult, VerificationOutcome
from shared.trajectories import TrajectoryLogger


def runDeterministicGates(
    case: EvalCase,
    hypothesis: InvestigationResult,
) -> list[str]:
    issues: list[str] = []
    validIds = {log.log_id for log in case.raw_logs}
    citedIds = set(hypothesis.evidence_log_ids) | set(hypothesis.culprit_log_ids)
    missingIds = citedIds - validIds
    if missingIds:
        issues.append(f"Fabricated or missing log IDs: {sorted(missingIds)}")
    if hypothesis.divergence_step not in case.process_context.expected_sequence:
        issues.append(
            f"divergence_step '{hypothesis.divergence_step}' not in expected_sequence"
        )
    return issues


def buildVerifierPrompt(case: EvalCase, hypothesis: InvestigationResult, gateIssues: list[str]) -> str:
    rawLogs = json.dumps([log.model_dump() for log in case.raw_logs], indent=2)
    hypothesisJson = hypothesis.model_dump_json(indent=2)
    gateBlock = "\n".join(gateIssues) if gateIssues else "None"
    processBlock = json.dumps(case.process_context.model_dump(), indent=2)
    return (
        f"{VERIFIER_INSTRUCTIONS}\n\n"
        f"DETERMINISTIC GATE ISSUES:\n{gateBlock}\n\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"RAW LOGS:\n{rawLogs}\n\n"
        f"HYPOTHESIS:\n{hypothesisJson}\n\n"
        f"Return VerificationOutcome JSON:\n"
        f'{{"is_grounded": bool, "issues": [str], "result": InvestigationResult or null}}'
    )


def runVerifier(
    case: EvalCase,
    hypothesis: InvestigationResult,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
) -> VerificationOutcome:
    gateIssues = runDeterministicGates(case, hypothesis)
    prompt = buildVerifierPrompt(case, hypothesis, gateIssues)
    if trajectory:
        trajectory.log(
            agent="verifier",
            event="verification_started",
            instructions=VERIFIER_INSTRUCTIONS,
            inputPayload={
                "hypothesis": hypothesis.model_dump(mode="json"),
                "deterministic_gate_issues": gateIssues,
            },
        )
    callResult: LlmCallResult = client.completeJson(
        prompt,
        VerificationOutcome,
        stage="stage3_verifier",
    )
    outcome = VerificationOutcome.model_validate(callResult.parsed.model_dump())
    if gateIssues:
        mergedIssues = list(dict.fromkeys(gateIssues + outcome.issues))
        outcome = outcome.model_copy(update={"issues": mergedIssues, "is_grounded": False})
    if trajectory:
        trajectory.log(
            agent="verifier",
            event="verification_complete",
            outputPayload=outcome.model_dump(mode="json"),
            feedback="; ".join(outcome.issues) if outcome.issues else "grounded",
        )
    return outcome
