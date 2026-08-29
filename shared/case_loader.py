"""Load evaluation cases and strip analysis-only fields before LLM use."""

from __future__ import annotations

import json
from pathlib import Path

from shared.schemas import EvalCase, GroundTruth, LlmEvalCase

CASES_DIR = Path(__file__).resolve().parent.parent / "data" / "cases"
BENCHMARK_CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 16))

FORBIDDEN_LLM_KEYS = frozenset(
    {
        "meta",
        "ground_truth",
        "decoy_diagnosis",
        "baseline_hypothesis",
        "expected_winner",
        "failure_pattern",
        "difficulty_factors",
        "difficulty",
        "decoy_type",
        "composite_score",
    }
)


def loadCase(path: Path) -> EvalCase:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "meta" in data and "expected_winner" in data["meta"]:
        data["meta"]["baseline_hypothesis"] = data["meta"].pop("expected_winner")
    return EvalCase.model_validate(data)


def loadAllCases(casesDir: Path | None = None) -> list[EvalCase]:
    directory = casesDir or CASES_DIR
    cases: list[EvalCase] = []
    for caseId in BENCHMARK_CASE_IDS:
        path = directory / f"{caseId}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing benchmark case file: {path}")
        cases.append(loadCase(path))
    return cases


def stripForLlm(case: EvalCase) -> LlmEvalCase:
    return LlmEvalCase(
        case_id=case.case_id,
        process_context=case.process_context,
        raw_logs=case.raw_logs,
    )


def serializeForLlm(case: EvalCase) -> str:
    return stripForLlm(case).model_dump_json(indent=2)


def assertLlmPayloadIsClean(payload: str) -> None:
    lowered = payload.lower()
    for key in FORBIDDEN_LLM_KEYS:
        if f'"{key}"' in lowered or f"'{key}'" in lowered:
            raise ValueError(f"Forbidden analysis key '{key}' found in LLM payload")


def getValidLogIds(case: EvalCase) -> set[str]:
    return {log.log_id for log in case.raw_logs}


def getGroundTruth(case: EvalCase) -> GroundTruth:
    return case.ground_truth
