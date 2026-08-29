"""Load holdout evaluation cases (case_16+) — separate from development benchmark."""

from __future__ import annotations

from pathlib import Path

from shared.case_loader import loadCase
from shared.schemas import EvalCase

HOLDOUT_DIR = Path(__file__).resolve().parent.parent / "data" / "holdout"
HOLDOUT_CASE_IDS = tuple(f"case_{index}" for index in range(16, 24))


def loadAllHoldoutCases(holdoutDir: Path | None = None) -> list[EvalCase]:
    directory = holdoutDir or HOLDOUT_DIR
    cases: list[EvalCase] = []
    for caseId in HOLDOUT_CASE_IDS:
        path = directory / f"{caseId}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing holdout case file: {path}")
        cases.append(loadCase(path))
    return cases
