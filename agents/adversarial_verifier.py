"""Adversarial Verifier — causal burden-of-proof gate on baseline vs agent."""

from __future__ import annotations

import json

from agents.hypothesis_board import candidateToInvestigation, findCandidate
from agents.verifier import runDeterministicGates
from shared.case_loader import getValidLogIds
from shared.llm import GeminiClient, LlmCallResult
from shared.prompts import ADVERSARIAL_VERIFIER_INSTRUCTIONS
from shared.schemas import (
    AdversarialVerificationOutcome,
    EvalCase,
    HypothesisBoard,
    InvestigationResult,
)
from shared.trajectories import TrajectoryLogger

BASELINE_ID = "baseline"


def buildAdversarialVerifierPrompt(
    case: EvalCase,
    board: HypothesisBoard,
    gateIssuesByCandidate: dict[str, list[str]],
) -> str:
    baseline = findCandidate(board, BASELINE_ID)
    agent = findCandidate(board, board.leading_hypothesis_id)
    rawLogs = json.dumps([log.model_dump() for log in case.raw_logs], indent=2)
    processBlock = json.dumps(case.process_context.model_dump(), indent=2)
    sequenceBlock = json.dumps(case.process_context.expected_sequence, indent=2)
    baselineBlock = baseline.model_dump_json(indent=2) if baseline else "{}"
    agentBlock = agent.model_dump_json(indent=2) if agent else "{}"
    baselineGateIssues = gateIssuesByCandidate.get(BASELINE_ID, [])
    agentGateIssues = gateIssuesByCandidate.get(board.leading_hypothesis_id, [])
    return (
        f"{ADVERSARIAL_VERIFIER_INSTRUCTIONS}\n\n"
        f"EXPECTED SEQUENCE (use for causal ordering, not timestamp alone):\n{sequenceBlock}\n\n"
        f"HYPOTHESIS A — BASELINE (preserve unless Agent has stronger causal evidence):\n"
        f"hypothesis_id: {BASELINE_ID}\n"
        f"DETERMINISTIC GATE ISSUES:\n{json.dumps(baselineGateIssues, indent=2)}\n"
        f"{baselineBlock}\n\n"
        f"HYPOTHESIS B — AGENT (replace A only with causally earlier divergence + log proof):\n"
        f"hypothesis_id: {board.leading_hypothesis_id}\n"
        f"DETERMINISTIC GATE ISSUES:\n{json.dumps(agentGateIssues, indent=2)}\n"
        f"{agentBlock}\n\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"RAW LOGS:\n{rawLogs}\n"
    )


def divergenceStepIndex(step: str, expectedSequence: list[str]) -> int | None:
    normalized = step.strip().lower()
    for index, sequenceStep in enumerate(expectedSequence):
        if sequenceStep.strip().lower() == normalized:
            return index
    return None


def rejectionCitesLogEvidence(rejectionReasons: list[str], validLogIds: set[str]) -> bool:
    if not rejectionReasons:
        return False
    combined = " ".join(rejectionReasons)
    return any(logId in combined for logId in validLogIds)


def isDownstreamDivergence(
    agentStep: str,
    baselineStep: str,
    expectedSequence: list[str],
) -> bool:
    agentIndex = divergenceStepIndex(agentStep, expectedSequence)
    baselineIndex = divergenceStepIndex(baselineStep, expectedSequence)
    if agentIndex is None or baselineIndex is None:
        return False
    return agentIndex > baselineIndex


def enforceCausalBurdenOfProof(
    outcome: AdversarialVerificationOutcome,
    board: HypothesisBoard,
    validLogIds: set[str],
    expectedSequence: list[str],
) -> AdversarialVerificationOutcome:
    baseline = findCandidate(board, BASELINE_ID)
    agentId = board.leading_hypothesis_id
    if baseline is None:
        return outcome

    if outcome.selected_hypothesis_id == BASELINE_ID:
        return outcome.model_copy(update={"leading_rejected": False})

    agent = findCandidate(board, agentId)
    if agent is None or agentId == BASELINE_ID:
        return _retainBaseline(
            outcome,
            "No Agent hypothesis available; Baseline preserved.",
        )

    if outcome.selected_hypothesis_id != agentId:
        outcome = outcome.model_copy(update={"selected_hypothesis_id": agentId})

    citesProof = rejectionCitesLogEvidence(outcome.rejection_reasons, validLogIds)
    if not citesProof:
        return _retainBaseline(
            outcome,
            "Causal burden of proof not met: Agent override requires cited log evidence.",
        )

    if isDownstreamDivergence(agent.divergence_step, baseline.divergence_step, expectedSequence):
        return _retainBaseline(
            outcome,
            "Agent divergence is downstream of Baseline; downstream symptom cannot replace upstream failure.",
        )

    return outcome.model_copy(update={"leading_rejected": True})


def _retainBaseline(
    outcome: AdversarialVerificationOutcome,
    reason: str,
) -> AdversarialVerificationOutcome:
    return outcome.model_copy(
        update={
            "leading_rejected": False,
            "selected_hypothesis_id": BASELINE_ID,
            "issues": list(dict.fromkeys(outcome.issues + [reason])),
        }
    )


def runAdversarialVerifier(
    case: EvalCase,
    board: HypothesisBoard,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
    retryCount: int = 0,
) -> AdversarialVerificationOutcome:
    gateIssuesByCandidate: dict[str, list[str]] = {}
    for candidate in board.candidates:
        investigation = candidateToInvestigation(candidate)
        gateIssuesByCandidate[candidate.hypothesis_id] = runDeterministicGates(case, investigation)

    prompt = buildAdversarialVerifierPrompt(case, board, gateIssuesByCandidate)
    baseline = findCandidate(board, BASELINE_ID)
    agent = findCandidate(board, board.leading_hypothesis_id)
    if trajectory:
        trajectory.log(
            agent="verifier",
            event="verification_started",
            instructions=ADVERSARIAL_VERIFIER_INSTRUCTIONS,
            inputPayload={
                "hypothesis_a_id": BASELINE_ID,
                "hypothesis_b_id": board.leading_hypothesis_id,
                "hypothesis_a": baseline.model_dump(mode="json") if baseline else {},
                "hypothesis_b": agent.model_dump(mode="json") if agent else {},
                "expected_sequence": case.process_context.expected_sequence,
                "deterministic_gate_issues": gateIssuesByCandidate,
            },
            retryCount=retryCount,
        )
    callResult: LlmCallResult = client.completeJson(
        prompt,
        AdversarialVerificationOutcome,
        stage="stage3_verifier_adversarial",
    )
    outcome = AdversarialVerificationOutcome.model_validate(callResult.parsed.model_dump())
    outcome = normalizeOutcome(outcome, case, board, gateIssuesByCandidate)
    if trajectory:
        feedback = "baseline_rejected" if outcome.leading_rejected else "baseline_retained"
        trajectory.log(
            agent="verifier",
            event="verification_complete",
            outputPayload=outcome.model_dump(mode="json"),
            feedback=feedback,
            retryCount=retryCount,
        )
    return outcome


def normalizeOutcome(
    outcome: AdversarialVerificationOutcome,
    case: EvalCase,
    board: HypothesisBoard,
    gateIssuesByCandidate: dict[str, list[str]],
) -> AdversarialVerificationOutcome:
    validLogIds = getValidLogIds(case)
    selected = findCandidate(board, outcome.selected_hypothesis_id)
    if selected is None:
        fallback = findCandidate(board, BASELINE_ID) or board.candidates[0]
        outcome = outcome.model_copy(
            update={
                "selected_hypothesis_id": fallback.hypothesis_id,
                "issues": outcome.issues + ["Selected hypothesis id was invalid; fell back."],
            }
        )

    outcome = enforceCausalBurdenOfProof(
        outcome,
        board,
        validLogIds,
        case.process_context.expected_sequence,
    )
    selected = findCandidate(board, outcome.selected_hypothesis_id)
    assert selected is not None

    gateIssues = gateIssuesByCandidate.get(outcome.selected_hypothesis_id, [])
    if gateIssues:
        mergedIssues = list(dict.fromkeys(gateIssues + outcome.issues))
        outcome = outcome.model_copy(update={"issues": mergedIssues})

    result = candidateToInvestigation(selected)
    return outcome.model_copy(update={"result": result})


def legacyRunVerifier(
    case: EvalCase,
    hypothesis: InvestigationResult,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
) -> InvestigationResult:
    """Unused in Stage 3 — kept for import stability in tests if any."""
    from agents.verifier import runVerifier
    from shared.schemas import VerificationOutcome

    outcome: VerificationOutcome = runVerifier(case, hypothesis, client, trajectory=trajectory)
    if outcome.result is not None:
        return outcome.result
    return hypothesis
