"""Read-only benchmark evaluation summary for the UI — aggregate metrics only."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
EVAL_SUBMISSION_PATH = ROOT_DIR / "results" / "eval_submission.json"
EVAL_HOLDOUT_PATH = ROOT_DIR / "results" / "eval_holdout.json"

METRIC_LABELS = {
    "failure_point": "Divergence accuracy",
    "root_cause": "Root-cause accuracy",
    "evidence_recall": "Evidence recall",
    "evidence_precision": "Evidence precision",
    "no_fabricated": "No-fabrication",
}


class BenchmarkMetricRow(BaseModel):
    label: str
    value_percent: float


class HoldoutOverview(BaseModel):
    case_count: int
    stage_0_iqs_percent: float
    stage_3_iqs_percent: float
    delta_pp: float
    source: str
    note: str = (
        "Unseen holdout benchmark (cases 16–23). Never used for prompt, gate, or tuning decisions. "
        "Reported separately to measure generalization under distribution shift."
    )


class BenchmarkOverview(BaseModel):
    case_count: int
    stage_0_iqs_percent: float
    stage_3_iqs_percent: float
    delta_pp: float
    metrics: list[BenchmarkMetricRow] = Field(default_factory=list)
    source: str
    note: str = (
        "Aggregate scores across the 15-case development benchmark at Stage 3. "
        "These are evaluation metrics, not predictions for individual incidents."
    )
    holdout: HoldoutOverview | None = None


def _loadStageMeans(path: Path) -> tuple[float, float, int] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    stageMeans = payload.get("stage_means_iqs", {})
    stage0 = stageMeans.get("0")
    stage3 = stageMeans.get("3")
    if stage0 is None or stage3 is None:
        return None
    caseCount = len(payload.get("cases", {}))
    return float(stage0), float(stage3), caseCount


def _aggregateStage3Metrics(cases: dict) -> list[BenchmarkMetricRow]:
    breakdownTotals: dict[str, list[float]] = {key: [] for key in METRIC_LABELS}
    for casePayload in cases.values():
        stage3Payload = casePayload.get("stage_3")
        if not stage3Payload:
            continue
        breakdown = stage3Payload.get("score_breakdown", {})
        for key in METRIC_LABELS:
            if key in breakdown:
                breakdownTotals[key].append(float(breakdown[key]))

    metrics: list[BenchmarkMetricRow] = []
    for key, label in METRIC_LABELS.items():
        values = breakdownTotals[key]
        if not values:
            continue
        metrics.append(
            BenchmarkMetricRow(
                label=label,
                value_percent=round(sum(values) / len(values) * 100, 2),
            )
        )
    return metrics


def loadHoldoutOverview() -> HoldoutOverview | None:
    loaded = _loadStageMeans(EVAL_HOLDOUT_PATH)
    if loaded is None:
        return None
    stage0, stage3, caseCount = loaded
    return HoldoutOverview(
        case_count=caseCount,
        stage_0_iqs_percent=round(stage0, 2),
        stage_3_iqs_percent=round(stage3, 2),
        delta_pp=round(stage3 - stage0, 2),
        source=str(EVAL_HOLDOUT_PATH.relative_to(ROOT_DIR)),
    )


def loadBenchmarkOverview() -> BenchmarkOverview | None:
    if not EVAL_SUBMISSION_PATH.exists():
        return None

    payload = json.loads(EVAL_SUBMISSION_PATH.read_text(encoding="utf-8"))
    stageMeans = payload.get("stage_means_iqs", {})
    stage0 = stageMeans.get("0")
    stage3 = stageMeans.get("3")
    if stage0 is None or stage3 is None:
        return None

    cases = payload.get("cases", {})
    stage3CaseCount = sum(1 for casePayload in cases.values() if casePayload.get("stage_3"))
    metrics = _aggregateStage3Metrics(cases)

    return BenchmarkOverview(
        case_count=stage3CaseCount or len(cases),
        stage_0_iqs_percent=round(float(stage0), 2),
        stage_3_iqs_percent=round(float(stage3), 2),
        delta_pp=round(float(stage3) - float(stage0), 2),
        metrics=metrics,
        source=str(EVAL_SUBMISSION_PATH.relative_to(ROOT_DIR)),
        holdout=loadHoldoutOverview(),
    )
