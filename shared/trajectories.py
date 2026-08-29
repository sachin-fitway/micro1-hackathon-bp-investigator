"""Trajectory logging for hackathon agent deliverables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRAJECTORIES_DIR = Path(__file__).resolve().parent.parent / "trajectories"


class TrajectoryLogger:
    def __init__(self, caseId: str, stage: str, trajectoriesDir: Path | None = None):
        self.case_id = caseId
        self.stage = stage
        directory = trajectoriesDir or TRAJECTORIES_DIR
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{caseId}_stage{stage}.jsonl"
        self._step = 0

    def log(
        self,
        agent: str,
        event: str,
        *,
        instructions: str = "",
        inputPayload: dict[str, Any] | None = None,
        outputPayload: dict[str, Any] | None = None,
        feedback: str = "",
        retryCount: int = 0,
        humanCheckpoint: bool = False,
    ) -> None:
        self._step += 1
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "case_id": self.case_id,
            "stage": self.stage,
            "step": self._step,
            "agent": agent,
            "event": event,
            "instructions": instructions,
            "input": inputPayload or {},
            "output": outputPayload or {},
            "feedback": feedback,
            "retry_count": retryCount,
            "human_checkpoint": humanCheckpoint,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    @property
    def file_path(self) -> Path:
        return self.path
