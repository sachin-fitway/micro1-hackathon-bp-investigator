"""Stage 3 orchestrator: baseline + challenger + adjudication verifier."""

from __future__ import annotations

from agents.adjudication_verifier import runAdjudicationVerifier
from agents.preprocess import buildTimeline
from agents.rule_checker import runRuleChecker
from baseline import runBaselineRaw
from shared.llm import GeminiClient
from shared.schemas import EvalCase, InvestigationResult
from shared.trajectories import TrajectoryLogger


def runWorkflowFull(
    case: EvalCase,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
) -> InvestigationResult:
    timeline = buildTimeline(case.raw_logs)
    if trajectory:
        trajectory.log(
            agent="preprocess",
            event="timeline_built",
            instructions="Deterministic sort and group by correlation ID",
            outputPayload={
                "entity_count": len(timeline),
                "log_count": len(case.raw_logs),
            },
        )

    baseline = runBaselineRaw(case, client, trajectory=trajectory)
    challenger = runRuleChecker(case, timeline, client, trajectory=trajectory)

    if trajectory:
        trajectory.log(
            agent="orchestrator",
            event="hypotheses_prepared",
            outputPayload={
                "baseline": baseline.model_dump(mode="json"),
                "challenger": challenger.model_dump(mode="json"),
            },
        )

    adjudication = runAdjudicationVerifier(
        case,
        timeline,
        baseline,
        challenger,
        client,
        trajectory=trajectory,
    )

    decisionEvent = (
        "adjudication_keep_baseline"
        if adjudication.decision == "keep_baseline"
        else "adjudication_override_baseline"
    )
    if trajectory:
        trajectory.log(
            agent="orchestrator",
            event=decisionEvent,
            outputPayload=adjudication.selected_hypothesis.model_dump(mode="json"),
            feedback=(
                f"decision={adjudication.decision}; "
                f"confidence={adjudication.confidence}; "
                f"why={adjudication.comparison.why_selected}"
            ),
        )

    return adjudication.selected_hypothesis
