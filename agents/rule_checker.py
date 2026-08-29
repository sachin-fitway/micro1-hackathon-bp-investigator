"""Rule Checker agent — generates competing hypotheses from timeline."""

from __future__ import annotations

import json

from agents.preprocess import timelineToPromptBlock
from shared.llm import GeminiClient, LlmCallResult
from shared.prompts import MULTI_HYPOTHESIS_RULE_CHECKER_INSTRUCTIONS, RULE_CHECKER_INSTRUCTIONS
from shared.schemas import EvalCase, HypothesisBoard, InvestigationResult, TimelineGroup
from shared.trajectories import TrajectoryLogger


def buildMultiHypothesisPrompt(
    case: EvalCase,
    timeline: list[TimelineGroup],
    baseline: InvestigationResult | None = None,
    feedback: str = "",
) -> str:
    processBlock = json.dumps(case.process_context.model_dump(), indent=2)
    timelineBlock = timelineToPromptBlock(timeline)
    feedbackBlock = f"\nVERIFIER FEEDBACK (address in new hypotheses):\n{feedback}\n" if feedback else ""
    baselineBlock = ""
    if baseline is not None:
        baselineBlock = (
            "\nBASELINE DIAGNOSIS (preserved separately — analyze but do not duplicate):\n"
            f"{baseline.model_dump_json(indent=2)}\n"
        )
    return (
        f"{MULTI_HYPOTHESIS_RULE_CHECKER_INSTRUCTIONS}\n"
        f"{feedbackBlock}"
        f"{baselineBlock}\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"ORDERED TIMELINE:\n{timelineBlock}\n"
    )


def buildLegacyRuleCheckerPrompt(
    case: EvalCase,
    timeline: list[TimelineGroup],
    feedback: str = "",
) -> str:
    processBlock = json.dumps(case.process_context.model_dump(), indent=2)
    timelineBlock = timelineToPromptBlock(timeline)
    feedbackBlock = f"\nVERIFIER FEEDBACK (address these):\n{feedback}\n" if feedback else ""
    return (
        f"{RULE_CHECKER_INSTRUCTIONS}\n"
        f"{feedbackBlock}\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"ORDERED TIMELINE:\n{timelineBlock}\n\n"
        f"Return InvestigationResult JSON."
    )


def runHypothesisBoard(
    case: EvalCase,
    timeline: list[TimelineGroup],
    client: GeminiClient,
    baseline: InvestigationResult | None = None,
    trajectory: TrajectoryLogger | None = None,
    feedback: str = "",
    retryCount: int = 0,
) -> HypothesisBoard:
    prompt = buildMultiHypothesisPrompt(case, timeline, baseline=baseline, feedback=feedback)
    if trajectory:
        trajectory.log(
            agent="rule_checker",
            event="prompt_built",
            instructions=MULTI_HYPOTHESIS_RULE_CHECKER_INSTRUCTIONS,
            inputPayload={
                "case_id": case.case_id,
                "entity_count": len(timeline),
                "has_baseline": baseline is not None,
                "feedback": feedback,
            },
            retryCount=retryCount,
        )
    stageLabel = "stage2_rule_checker_multi" if baseline is None else "stage3_rule_checker_multi"
    callResult: LlmCallResult = client.completeJson(
        prompt,
        HypothesisBoard,
        stage=stageLabel,
    )
    board = HypothesisBoard.model_validate(callResult.parsed.model_dump())
    if trajectory:
        trajectory.log(
            agent="rule_checker",
            event="hypothesis_board",
            outputPayload=board.model_dump(mode="json"),
            feedback=f"parse_retries={callResult.retry_count}",
            retryCount=retryCount,
        )
    return board


def runRuleChecker(
    case: EvalCase,
    timeline: list[TimelineGroup],
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
    feedback: str = "",
    retryCount: int = 0,
) -> InvestigationResult:
    """Multi-hypothesis board; return leading candidate as InvestigationResult."""
    board = runHypothesisBoard(
        case,
        timeline,
        client,
        baseline=None,
        trajectory=trajectory,
        feedback=feedback,
        retryCount=retryCount,
    )
    leading = _selectLeadingCandidate(board)
    if trajectory:
        trajectory.log(
            agent="rule_checker",
            event="hypothesis_selected",
            outputPayload=leading.model_dump(mode="json"),
            feedback=f"leading_id={board.leading_hypothesis_id}",
            retryCount=retryCount,
        )
    return InvestigationResult(
        divergence_step=leading.divergence_step,
        root_cause_category=leading.root_cause_category,
        culprit_log_ids=leading.culprit_log_ids,
        evidence_log_ids=leading.evidence_log_ids,
        explanation=leading.explanation,
    )


def _selectLeadingCandidate(board: HypothesisBoard):
    for candidate in board.candidates:
        if candidate.hypothesis_id == board.leading_hypothesis_id:
            return candidate
    return board.candidates[0]
