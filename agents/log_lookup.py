"""Deterministic log lookup tool for evidence-grounded reporting."""

from __future__ import annotations

from shared.schemas import LogEntry


class LogLookupError(ValueError):
    """Raised when a log ID is unknown or invalid."""


class LogLookupTool:
    """Read-only index over raw case logs."""

    def __init__(self, rawLogs: list[LogEntry]):
        self._index = {log.log_id: log for log in rawLogs}

    @property
    def validLogIds(self) -> frozenset[str]:
        return frozenset(self._index)

    def fetch_log_details(self, logId: str) -> LogEntry:
        """Return a copy of the log record for logId, or reject unknown IDs."""
        normalized = logId.strip()
        if not normalized:
            raise LogLookupError("Log ID must be non-empty")
        if normalized not in self._index:
            raise LogLookupError(f"Unknown log ID: {normalized}")
        return LogEntry.model_validate(self._index[normalized].model_dump(mode="json"))

    def fetchMany(self, logIds: list[str]) -> tuple[dict[str, LogEntry], list[str]]:
        retrieved: dict[str, LogEntry] = {}
        unknown: list[str] = []
        for logId in logIds:
            try:
                retrieved[logId] = self.fetch_log_details(logId)
            except LogLookupError:
                unknown.append(logId)
        return retrieved, unknown
