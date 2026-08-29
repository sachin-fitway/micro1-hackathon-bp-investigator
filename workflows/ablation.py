"""Ablation ladder runners for stages 0–3."""

from __future__ import annotations

import json

from agents.main_agent import runWorkflowFull
from agents.preprocess import buildTimeline, timelineToPromptBlock
from agents.rule_checker import runRuleChecker
from baseline import runBaselineRaw
from shared.case_loader import stripForLlm
from shared.llm import GeminiClient
from shared.prompts import STRUCTURED_BASELINE_INSTRUCTIONS
from shared.schemas import EvalCase, InvestigationResult
from shared.trajectories import TrajectoryLogger


def runStage0BaselineRaw(
    case: EvalCase,
    client: GeminiClient,
) -> InvestigationResult:
    trajectory = TrajectoryLogger(case.case_id, stage="0")
    return runBaselineRaw(case, client, trajectory)


def runStage1BaselineStructured(
    case: EvalCase,
    client: GeminiClient,
) -> InvestigationResult:
    trajectory = TrajectoryLogger(case.case_id, stage="1")
    timeline = buildTimeline(case.raw_logs)
    trajectory.log(
        agent="preprocess",
        event="timeline_built",
        instructions="Deterministic sort/group for structured baseline",
        outputPayload={"entity_count": len(timeline)},
    )
    llmCase = stripForLlm(case)
    prompt = (
        f"{STRUCTURED_BASELINE_INSTRUCTIONS}\n\n"
        f"CASE DATA:\n{json.dumps(llmCase.model_dump(mode='json'), indent=2)}\n\n"
        f"RECONSTRUCTED TIMELINE:\n{timelineToPromptBlock(timeline)}\n"
    )
    trajectory.log(
        agent="baseline_structured",
        event="prompt_built",
        instructions=STRUCTURED_BASELINE_INSTRUCTIONS,
        inputPayload={"case_id": case.case_id},
    )
    callResult = client.completeJson(prompt, InvestigationResult, stage="stage1_baseline_structured")
    result = InvestigationResult.model_validate(callResult.parsed.model_dump())
    trajectory.log(
        agent="baseline_structured",
        event="llm_response",
        outputPayload=result.model_dump(mode="json"),
        retryCount=callResult.retry_count,
    )
    return result


def runStage2RulesOnly(
    case: EvalCase,
    client: GeminiClient,
) -> InvestigationResult:
    trajectory = TrajectoryLogger(case.case_id, stage="2")
    timeline = buildTimeline(case.raw_logs)
    trajectory.log(
        agent="preprocess",
        event="timeline_built",
        outputPayload={"entity_count": len(timeline)},
    )
    return runRuleChecker(case, timeline, client, trajectory=trajectory)


def runStage3WorkflowFull(
    case: EvalCase,
    client: GeminiClient,
) -> InvestigationResult:
    trajectory = TrajectoryLogger(case.case_id, stage="3")
    return runWorkflowFull(case, client, trajectory)


STAGE_RUNNERS = {
    0: runStage0BaselineRaw,
    1: runStage1BaselineStructured,
    2: runStage2RulesOnly,
    3: runStage3WorkflowFull,
}

STAGE_LABELS = {
    0: "Baseline (raw single prompt)",
    1: "Baseline (structured timeline)",
    2: "Rules only (preprocess + rule_checker)",
    3: "Full workflow (baseline + challenger + adjudication verifier)",
}
