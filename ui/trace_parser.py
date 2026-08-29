"""Sanitize trajectory JSONL into UI-safe investigation trace phases."""

from __future__ import annotations

import json
from pathlib import Path

from ui.models import PipelinePhase, TraceStepDetail

PHASE_ORDER = (
    ("logs", "Logs"),
    ("diagnosis", "Diagnosis"),
    ("safety_gates", "Safety Gates"),
    ("evidence_retrieval", "Evidence Retrieval"),
    ("post_mortem", "Post-Mortem"),
)

EVENTS_TO_SKIP = frozenset({"prompt_built"})


def _loadLatestRunRecords(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    if not records:
        return []
    lastReset = 0
    for index, record in enumerate(records):
        if record.get("step") == 1 and record.get("event") == "timeline_built":
            lastReset = index
    return records[lastReset:]


def _extractLogIds(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    ids: list[str] = []
    for key in ("culprit_log_ids", "evidence_log_ids", "retrieved_evidence", "retrieved_culprits"):
        value = payload.get(key)
        if isinstance(value, list):
            ids.extend(str(item) for item in value)
    output = payload.get("output")
    if isinstance(output, dict):
        for key in ("culprit_log_ids", "evidence_log_ids"):
            value = output.get(key)
            if isinstance(value, list):
                ids.extend(str(item) for item in value)
    return list(dict.fromkeys(ids))


def _summarizeRecord(record: dict) -> TraceStepDetail:
    agent = record.get("agent", "")
    event = record.get("event", "")
    output = record.get("output") or {}
    feedback = record.get("feedback", "")
    label = f"{agent}.{event}" if agent else event
    summary = feedback or ""
    decision = ""
    gateBlocks: list[str] = []

    if event == "timeline_built":
        count = output.get("log_count", "?")
        summary = f"Built ordered timeline from {count} raw logs."
    elif event == "llm_response" and agent == "baseline":
        step = output.get("divergence_step", "")
        category = output.get("root_cause_category", "")
        summary = f"Baseline diagnosis: divergence at '{step}', category '{category}'."
    elif event == "hypothesis_selected":
        step = output.get("divergence_step", "")
        summary = f"Challenger hypothesis selected: divergence at '{step}'."
    elif event == "hypotheses_prepared":
        summary = "Baseline and challenger hypotheses prepared for adjudication."
    elif event == "adjudication_complete":
        decision = output.get("decision", "")
        confidence = output.get("confidence", "")
        why = (output.get("comparison") or {}).get("why_selected", "")
        gateBlocks = list(output.get("deterministic_blocks") or [])
        summary = f"Adjudication decision: {decision} (confidence {confidence}). {why[:240]}"
    elif event in ("adjudication_keep_baseline", "adjudication_override_baseline"):
        decision = "keep_baseline" if "keep" in event else "override_baseline"
        summary = feedback[:280] if feedback else f"Final decision: {decision}."
    elif event == "logs_retrieved":
        evidence = output.get("retrieved_evidence") or []
        culprits = output.get("retrieved_culprits") or []
        summary = f"Hydrated {len(evidence)} evidence and {len(culprits)} culprit logs from source case logs."
    elif event == "report_generated":
        summary = f"Post-mortem report generated ({output.get('markdown_length', '?')} chars)."
    elif not summary:
        summary = f"{label} completed."

    return TraceStepDetail(
        label=label,
        status="complete",
        summary=summary,
        agent=agent,
        event=event,
        evidence_log_ids=_extractLogIds(output),
        decision=decision,
        gate_blocks=gateBlocks,
    )


def _assignPhase(record: dict) -> str:
    agent = record.get("agent", "")
    event = record.get("event", "")
    if agent == "preprocess":
        return "logs"
    if agent == "baseline" or (agent == "rule_checker" and event != "logs_retrieved"):
        return "diagnosis"
    if agent in ("verifier", "orchestrator") and "adjudication" in event:
        return "safety_gates"
    if agent == "post_mortem_reporter" and event == "logs_retrieved":
        return "evidence_retrieval"
    if agent == "post_mortem_reporter" and event == "report_generated":
        return "post_mortem"
    if agent == "post_mortem_reporter":
        return "evidence_retrieval"
    return "diagnosis"


def buildPipelinePhases(
    investigationTrajectoryPath: Path | None,
    postMortemTrajectoryPath: Path | None,
) -> list[PipelinePhase]:
    phaseDetails: dict[str, list[TraceStepDetail]] = {phaseId: [] for phaseId, _ in PHASE_ORDER}
    paths = [path for path in (investigationTrajectoryPath, postMortemTrajectoryPath) if path]
    for path in paths:
        for record in _loadLatestRunRecords(path):
            if record.get("event") in EVENTS_TO_SKIP:
                continue
            phaseId = _assignPhase(record)
            phaseDetails[phaseId].append(_summarizeRecord(record))

    phases: list[PipelinePhase] = []
    for phaseId, title in PHASE_ORDER:
        details = phaseDetails[phaseId]
        status = "complete" if details else "pending"
        phases.append(
            PipelinePhase(
                phase_id=phaseId,
                title=title,
                status=status,
                details=details,
            )
        )
    return phases
