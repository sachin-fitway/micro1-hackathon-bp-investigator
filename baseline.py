"""Stage 0: single-prompt baseline on raw logs."""

from __future__ import annotations

import json

from shared.case_loader import serializeForLlm, stripForLlm
from shared.llm import GeminiClient, LlmCallResult
from shared.prompts import BASELINE_INSTRUCTIONS
from shared.schemas import EvalCase, InvestigationResult
from shared.trajectories import TrajectoryLogger


def buildBaselinePrompt(case: EvalCase) -> str:
    llmCase = stripForLlm(case)
    payload = json.dumps(llmCase.model_dump(mode="json"), indent=2)
    return f"{BASELINE_INSTRUCTIONS}\n\nCASE DATA:\n{payload}"


def runBaselineRaw(
    case: EvalCase,
    client: GeminiClient,
    trajectory: TrajectoryLogger | None = None,
) -> InvestigationResult:
    prompt = buildBaselinePrompt(case)
    if trajectory:
        trajectory.log(
            agent="baseline",
            event="prompt_built",
            instructions=BASELINE_INSTRUCTIONS,
            inputPayload={"case_id": case.case_id, "log_count": len(case.raw_logs)},
        )
    callResult: LlmCallResult = client.completeJson(
        prompt,
        InvestigationResult,
        stage="stage0_baseline_raw",
    )
    result = InvestigationResult.model_validate(callResult.parsed.model_dump())
    if trajectory:
        trajectory.log(
            agent="baseline",
            event="llm_response",
            outputPayload=result.model_dump(mode="json"),
            feedback=f"parse_retries={callResult.retry_count}",
            retryCount=callResult.retry_count,
        )
    return result


def main() -> None:
    import argparse
    from pathlib import Path

    from shared.case_loader import loadCase

    parser = argparse.ArgumentParser(description="Run baseline on one case")
    parser.add_argument("--case", required=True, help="Path to case JSON")
    args = parser.parse_args()
    case = loadCase(Path(args.case))
    client = GeminiClient()
    trajectory = TrajectoryLogger(case.case_id, stage="0")
    result = runBaselineRaw(case, client, trajectory)
    print(result.model_dump_json(indent=2))
    print(f"Trajectory: {trajectory.file_path}")


if __name__ == "__main__":
    main()
