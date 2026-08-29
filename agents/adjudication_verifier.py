"""Stage 3 adjudication verifier — baseline vs challenger with deterministic gates."""

from __future__ import annotations

import json

from agents.adjudication_gates import buildLogTimestampMap, evaluateOverrideBlocks
from agents.preprocess import timelineToPromptBlock
from agents.verifier import runDeterministicGates
from shared.case_loader import getValidLogIds
from shared.llm import GeminiClient, LlmCallResult
from shared.prompts import ADJUDICATION_VERIFIER_INSTRUCTIONS
from shared.schemas import (
    CausalComparison,
    EvalCase,
    HypothesisAssessment,
    InvestigationResult,
    TimelineGroup,
    VerifierAdjudicationOutcome,
)
from shared.trajectories import TrajectoryLogger


def buildAdjudicationPrompt(
    case: EvalCase,
    timeline: list[TimelineGroup],
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    baselineGateIssues: list[str],
    challengerGateIssues: list[str],
) -> str:
    rawLogs = json.dumps([log.model_dump() for log in case.raw_logs], indent=2)
    processBlock = json.dumps(case.process_context.model_dump(), indent=2)
    sequenceBlock = json.dumps(case.process_context.expected_sequence, indent=2)
    timelineBlock = timelineToPromptBlock(timeline)
    baselineBlock = baseline.model_dump_json(indent=2)
    challengerBlock = challenger.model_dump_json(indent=2)
    return (
        f"{ADJUDICATION_VERIFIER_INSTRUCTIONS}\n\n"
        f"EXPECTED SEQUENCE (causal order — not timestamp alone):\n{sequenceBlock}\n\n"
        f"BASELINE DIAGNOSIS (DEFAULT — keep unless challenger is demonstrably stronger):\n"
        f"DETERMINISTIC GATE ISSUES: {json.dumps(baselineGateIssues, indent=2)}\n"
        f"{baselineBlock}\n\n"
        f"CHALLENGER DIAGNOSIS (from rule_checker — must beat baseline on causal evidence):\n"
        f"DETERMINISTIC GATE ISSUES: {json.dumps(challengerGateIssues, indent=2)}\n"
        f"{challengerBlock}\n\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"ORDERED TIMELINE:\n{timelineBlock}\n\n"
        f"RAW LOGS:\n{rawLogs}\n"
    )


def applyDeterministicAdjudication(
    outcome: VerifierAdjudicationOutcome,
    case: EvalCase,
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    expectedSequence: list[str],
    baselineGateIssues: list[str],
    challengerGateIssues: list[str],
    validLogIds: set[str],
) -> VerifierAdjudicationOutcome:
    comparisonText = " ".join(
        [
            outcome.comparison.why_selected,
            *outcome.comparison.baseline_causal_chain,
            *outcome.comparison.challenger_causal_chain,
        ]
    )
    blocks = evaluateOverrideBlocks(
        baseline,
        challenger,
        expectedSequence,
        baselineGateIssues,
        challengerGateIssues,
        comparisonText,
        validLogIds,
        buildLogTimestampMap(case),
    )

    if outcome.decision == "override_baseline" and blocks:
        return outcome.model_copy(
            update={
                "decision": "keep_baseline",
                "selected_hypothesis": baseline,
                "deterministic_blocks": blocks,
                "comparison": outcome.comparison.model_copy(
                    update={
                        "why_selected": (
                            f"Deterministic gate kept baseline: {' | '.join(blocks)}"
                        ),
                    }
                ),
            }
        )

    if outcome.decision == "keep_baseline":
        return outcome.model_copy(update={"selected_hypothesis": baseline, "deterministic_blocks": blocks})

    return outcome.model_copy(
        update={
            "selected_hypothesis": challenger,
            "deterministic_blocks": blocks,
        }
    )


def runAdjudicationVerifier(
    case: EvalCase,
    timeline: list[TimelineGroup],
    baseline: InvestigationResult,
    challenger: InvestigationResult,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
) -> VerifierAdjudicationOutcome:
    baselineGateIssues = runDeterministicGates(case, baseline)
    challengerGateIssues = runDeterministicGates(case, challenger)
    validLogIds = getValidLogIds(case)

    prompt = buildAdjudicationPrompt(
        case,
        timeline,
        baseline,
        challenger,
        baselineGateIssues,
        challengerGateIssues,
    )

    if trajectory:
        trajectory.log(
            agent="verifier",
            event="adjudication_started",
            instructions=ADJUDICATION_VERIFIER_INSTRUCTIONS,
            inputPayload={
                "baseline": baseline.model_dump(mode="json"),
                "challenger": challenger.model_dump(mode="json"),
                "baseline_gate_issues": baselineGateIssues,
                "challenger_gate_issues": challengerGateIssues,
                "expected_sequence": case.process_context.expected_sequence,
            },
        )

    callResult: LlmCallResult = client.completeJson(
        prompt,
        VerifierAdjudicationOutcome,
        stage="stage3_verifier_adjudication",
    )
    outcome = VerifierAdjudicationOutcome.model_validate(callResult.parsed.model_dump())
    outcome = applyDeterministicAdjudication(
        outcome,
        case,
        baseline,
        challenger,
        case.process_context.expected_sequence,
        baselineGateIssues,
        challengerGateIssues,
        validLogIds,
    )

    if trajectory:
        trajectory.log(
            agent="verifier",
            event="adjudication_complete",
            outputPayload={
                "decision": outcome.decision,
                "confidence": outcome.confidence,
                "baseline_assessment": outcome.baseline_assessment.model_dump(mode="json"),
                "challenger_assessment": outcome.challenger_assessment.model_dump(mode="json"),
                "comparison": outcome.comparison.model_dump(mode="json"),
                "deterministic_blocks": outcome.deterministic_blocks,
                "selected_hypothesis": outcome.selected_hypothesis.model_dump(mode="json"),
            },
            feedback=outcome.comparison.why_selected,
        )

    return outcome


def defaultKeepBaselineOutcome(
    baseline: InvestigationResult,
    reason: str,
) -> VerifierAdjudicationOutcome:
    return VerifierAdjudicationOutcome(
        decision="keep_baseline",
        selected_hypothesis=baseline,
        baseline_assessment=HypothesisAssessment(valid=True, problems=[]),
        challenger_assessment=HypothesisAssessment(valid=False, problems=[reason]),
        comparison=CausalComparison(
            baseline_causal_chain=["Baseline preserved."],
            challenger_causal_chain=[],
            why_selected=reason,
        ),
        confidence=1.0,
        deterministic_blocks=[reason],
    )
