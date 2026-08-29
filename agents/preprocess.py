"""Deterministic log preprocessing — no LLM."""

from __future__ import annotations

import re
from datetime import datetime

from shared.schemas import LogEntry, TimelineGroup

CORRELATION_PATTERN = re.compile(
    r"(?:correlation_id|order_id|transaction_id|entity_id)[\"']?\s*[:=]\s*[\"']?([\w-]+)",
    re.IGNORECASE,
)


def parseTimestamp(timestamp: str) -> datetime:
    normalized = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def extractCorrelationId(logEntry: LogEntry) -> str:
    if "correlation_id" in logEntry.metadata:
        return str(logEntry.metadata["correlation_id"])
    match = CORRELATION_PATTERN.search(logEntry.message)
    if match:
        return match.group(1)
    for value in logEntry.metadata.values():
        if isinstance(value, str) and len(value) >= 4:
            return value
    return "unknown"


def sortLogsChronologically(logs: list[LogEntry]) -> list[LogEntry]:
    return sorted(logs, key=lambda entry: (parseTimestamp(entry.timestamp), entry.log_id))


def groupByEntity(logs: list[LogEntry]) -> list[TimelineGroup]:
    buckets: dict[str, list[LogEntry]] = {}
    for entry in logs:
        entityId = extractCorrelationId(entry)
        buckets.setdefault(entityId, []).append(entry)
    groups = []
    for entityId, entityLogs in sorted(buckets.items()):
        groups.append(
            TimelineGroup(
                entity_id=entityId,
                ordered_logs=sortLogsChronologically(entityLogs),
            )
        )
    return groups


def buildTimeline(logs: list[LogEntry]) -> list[TimelineGroup]:
    sortedLogs = sortLogsChronologically(logs)
    return groupByEntity(sortedLogs)


def timelineToPromptBlock(groups: list[TimelineGroup]) -> str:
    lines = []
    for group in groups:
        lines.append(f"Entity: {group.entity_id}")
        for entry in group.ordered_logs:
            lines.append(
                f"  [{entry.timestamp}] {entry.log_id} {entry.service}: {entry.message} "
                f"metadata={entry.metadata}"
            )
    return "\n".join(lines)
