"""Build incident-story presentation from existing diagnosis and trace data."""

from __future__ import annotations

import re

from shared.schemas import InvestigationResult, RootCauseCategory
from ui.models import (
    CausalChainNode,
    HydratedLogEntry,
    IncidentMetadata,
    IncidentStory,
    MechanismChainNode,
    PipelinePhase,
    ProcessStepView,
    StoryPhaseView,
    TraceStepDetail,
)

STORY_PHASE_ORDER = (
    ("analyze", "Analyze"),
    ("diagnose", "Diagnose"),
    ("validate", "Validate"),
    ("evidence_retrieval", "Evidence Retrieval"),
    ("report", "Report"),
)

LOADER_PHASE_COPY = (
    ("analyze", "Reading incident logs and reconstructing the workflow"),
    ("diagnose", "Identifying the divergence point and root cause"),
    ("validate", "Checking competing hypotheses and safety gates"),
    ("evidence_retrieval", "Retrieving the logs supporting the diagnosis"),
    ("report", "Generating the evidence-grounded post-mortem"),
)

ROOT_CAUSE_LABELS = {
    RootCauseCategory.SEQUENCE_SKIP.value: "Sequence skip",
    RootCauseCategory.FALSE_SUCCESS_SIGNAL.value: "False success signal",
    RootCauseCategory.CONFIG_DRIFT.value: "Configuration drift",
    RootCauseCategory.WEBHOOK_MISSING.value: "Missing webhook / event",
    RootCauseCategory.RACE_CONDITION.value: "Race condition",
    RootCauseCategory.DUPLICATE_PROCESSING.value: "Duplicate processing",
    RootCauseCategory.ENTITLEMENT_MISMATCH.value: "Entitlement mismatch",
    RootCauseCategory.TIMEOUT_STALL.value: "Timeout / stall",
    RootCauseCategory.METADATA_MESSAGE_CONFLICT.value: "Metadata / message conflict",
    RootCauseCategory.DOWNSTREAM_MASKS_UPSTREAM.value: "Downstream masks upstream",
}

ROOT_CAUSE_DESCRIPTIONS = {
    RootCauseCategory.SEQUENCE_SKIP.value: "Required workflow step was skipped or bypassed.",
    RootCauseCategory.FALSE_SUCCESS_SIGNAL.value: (
        "A step reported success even though its resulting state was inconsistent."
    ),
    RootCauseCategory.CONFIG_DRIFT.value: (
        "Configuration or policy caused the workflow to behave differently from the expected process."
    ),
    RootCauseCategory.WEBHOOK_MISSING.value: "A required downstream event was not observed.",
    RootCauseCategory.ENTITLEMENT_MISMATCH.value: (
        "The resulting entitlement or state did not match the expected state."
    ),
    RootCauseCategory.RACE_CONDITION.value: "Concurrent execution caused inconsistent process state.",
    RootCauseCategory.DUPLICATE_PROCESSING.value: "The same work was processed more than once.",
    RootCauseCategory.TIMEOUT_STALL.value: "A step stalled or timed out before completing.",
    RootCauseCategory.METADATA_MESSAGE_CONFLICT.value: (
        "Log metadata and message content pointed to different conclusions."
    ),
    RootCauseCategory.DOWNSTREAM_MASKS_UPSTREAM.value: (
        "A downstream symptom obscured the upstream divergence."
    ),
}

HEDGING_PATTERN = re.compile(r"\b(likely|probably|presumably|maybe|perhaps)\b", re.IGNORECASE)
IMPACT_CLAIM_PATTERN = re.compile(
    r"\b(lost sale|revenue loss|lost revenue|negative user experience|churn)\b",
    re.IGNORECASE,
)


def buildFailureTitle(diagnosis: InvestigationResult) -> str:
    step = humanizeStep(diagnosis.divergence_step)
    if step.endswith(" allocate"):
        step = step.replace(" allocate", " allocation")
    return f"{step.capitalize()} failed"


def buildConfidenceLabel(confidence: str | None) -> str:
    if confidence:
        return "High confidence"
    return "Adjudicated diagnosis"


def buildWhyBrief(
    diagnosis: InvestigationResult,
    metadata: IncidentMetadata,
    hydratedLogs: list[HydratedLogEntry],
) -> str:
    explanation = diagnosis.explanation.strip()
    if explanation:
        parts = re.split(r"(?<=[.!?])\s+", explanation)
        brief = parts[0].strip()
        if len(parts) > 1 and len(brief) < 120:
            brief = f"{brief} {parts[1].strip()}"
        if not HEDGING_PATTERN.search(diagnosis.explanation):
            brief = HEDGING_PATTERN.sub("", brief)
            brief = re.sub(r"\s{2,}", " ", brief).strip()
        return brief

    mechanism = buildEvidenceMechanismChain(diagnosis, hydratedLogs)
    if not mechanism:
        return (
            f"The process diverged at {humanizeStep(diagnosis.divergence_step)} "
            f"({describeCategory(diagnosis.root_cause_category.value)})."
        )
    return " ".join(node.label for node in mechanism[:3]) + "."


def humanizeStep(step: str) -> str:
    return step.replace("_", " ")


def humanizeCategory(category: str) -> str:
    return ROOT_CAUSE_LABELS.get(category, category.replace("_", " "))


def describeCategory(category: str) -> str:
    return ROOT_CAUSE_DESCRIPTIONS.get(category, f"Root cause category: {category.replace('_', ' ')}.")


def firstSentence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    match = re.match(r"^(.+?[.!?])(?:\s|$)", cleaned)
    return match.group(1) if match else cleaned[:220]


def buildWhyItFailed(
    diagnosis: InvestigationResult,
    metadata: IncidentMetadata,
    hydratedLogs: list[HydratedLogEntry],
    maxSentences: int = 4,
) -> str:
    explanation = diagnosis.explanation.strip()
    if explanation:
        parts = re.split(r"(?<=[.!?])\s+", explanation)
        selected = " ".join(parts[:maxSentences]).strip()
        if not HEDGING_PATTERN.search(diagnosis.explanation):
            selected = HEDGING_PATTERN.sub("", selected)
            selected = re.sub(r"\s{2,}", " ", selected).strip()
        return selected

    logById = {entry.log_id: entry for entry in hydratedLogs}
    stepLabel = humanizeStep(diagnosis.divergence_step)
    culpritLines: list[str] = []
    for logId in diagnosis.culprit_log_ids:
        if logId in logById:
            culpritLines.append(f"{logById[logId].service}: {logById[logId].message} ({logId})")
    if culpritLines:
        return (
            f"The process diverged at {stepLabel} ({describeCategory(diagnosis.root_cause_category.value)}). "
            f"Culprit evidence: {'; '.join(culpritLines)}."
        )
    return (
        f"The process diverged at {stepLabel}. "
        f"No culprit log messages were retrieved from the supplied logs."
    )


def buildHeadline(
    diagnosis: InvestigationResult,
    metadata: IncidentMetadata,
    hydratedLogs: list[HydratedLogEntry],
) -> str:
    """Legacy field — mirrors failure title for exports."""
    return buildFailureTitle(diagnosis)


def buildEvidenceMechanismChain(
    diagnosis: InvestigationResult,
    hydratedLogs: list[HydratedLogEntry],
) -> list[MechanismChainNode]:
    logById = {entry.log_id: entry for entry in hydratedLogs}
    orderedIds = list(dict.fromkeys(diagnosis.evidence_log_ids + diagnosis.culprit_log_ids))
    entries = [logById[logId] for logId in orderedIds if logId in logById]
    entries.sort(key=lambda entry: entry.timestamp)
    culpritSet = set(diagnosis.culprit_log_ids)
    failureIndex = next(
        (index for index, entry in enumerate(entries) if entry.log_id in culpritSet),
        -1,
    )
    nodes: list[MechanismChainNode] = []
    for index, entry in enumerate(entries):
        if entry.log_id in culpritSet:
            kind = "failure"
        elif failureIndex >= 0 and index > failureIndex:
            kind = "consequence"
        else:
            kind = "precursor"
        nodes.append(
            MechanismChainNode(
                label=entry.message,
                log_id=entry.log_id,
                kind=kind,
                service=entry.service,
            )
        )
    return nodes


def buildIncidentTitle(metadata: IncidentMetadata, diagnosis: InvestigationResult) -> str:
    processLabel = metadata.process_name.replace("_", " ")
    stepLabel = humanizeStep(diagnosis.divergence_step)
    return f"{processLabel} — failure at {stepLabel}"


def buildIncidentSummary(story: IncidentStory) -> str:
    evidence = " · ".join(story.evidence_log_ids) if story.evidence_log_ids else "(none)"
    return "\n".join([
        story.failure_title,
        "",
        f"Divergence: {story.divergence_step}",
        f"Why: {story.why_brief}",
        f"Root-cause category: {story.root_cause_label} ({story.root_cause_category})",
        f"Confidence: {story.confidence_label}",
        f"Evidence: {evidence}",
    ])


def buildProcessSteps(
    metadata: IncidentMetadata,
    diagnosis: InvestigationResult,
) -> list[ProcessStepView]:
    sequence = metadata.expected_sequence
    divergenceIndex = next(
        (index for index, step in enumerate(sequence) if step == diagnosis.divergence_step),
        -1,
    )
    steps: list[ProcessStepView] = []
    for index, step in enumerate(sequence):
        if index == divergenceIndex:
            state = "failed"
        elif divergenceIndex >= 0 and index > divergenceIndex:
            state = "downstream"
        else:
            state = "ok"
        steps.append(
            ProcessStepView(
                step=step,
                label=humanizeStep(step),
                state=state,
                culprit_log_ids=list(diagnosis.culprit_log_ids) if state == "failed" else [],
            )
        )
    return steps


def selectKeyEvidenceIds(diagnosis: InvestigationResult, limit: int = 3) -> list[str]:
    ordered: list[str] = []
    for logId in diagnosis.culprit_log_ids + diagnosis.evidence_log_ids:
        if logId not in ordered:
            ordered.append(logId)
        if len(ordered) >= limit:
            break
    return ordered


def _assignStoryPhase(detail: TraceStepDetail) -> str:
    event = detail.event
    agent = detail.agent
    if event == "timeline_built" or agent == "preprocess":
        return "analyze"
    if agent == "baseline":
        return "diagnose"
    if agent == "rule_checker" or agent in ("verifier", "orchestrator") or "adjudication" in event:
        return "validate"
    if event == "logs_retrieved":
        return "evidence_retrieval"
    if event == "report_generated":
        return "report"
    return "analyze"


def _humanPhaseDescription(phaseId: str, details: list[TraceStepDetail]) -> str:
    defaults = dict(LOADER_PHASE_COPY)
    if not details:
        return defaults.get(phaseId, "Phase completed.")
    for detail in reversed(details):
        if detail.summary and "." not in detail.label:
            return detail.summary
        if detail.summary and not detail.label.startswith(("baseline.", "rule_checker.", "orchestrator.")):
            return detail.summary
    cleaned = [detail.summary for detail in details if detail.summary]
    if cleaned:
        text = cleaned[-1]
        for prefix in ("baseline.", "rule_checker.", "orchestrator.", "verifier.", "post_mortem_reporter."):
            if prefix in text:
                continue
        return text
    return defaults.get(phaseId, "Phase completed.")


def _extractConfidence(details: list[TraceStepDetail]) -> str | None:
    for detail in details:
        if detail.event == "adjudication_complete" and detail.summary:
            match = re.search(r"confidence\s+([\d.]+)", detail.summary, re.IGNORECASE)
            if match:
                return match.group(1)
    return None


def buildStoryPhases(phases: list[PipelinePhase]) -> list[StoryPhaseView]:
    grouped: dict[str, list[TraceStepDetail]] = {phaseId: [] for phaseId, _ in STORY_PHASE_ORDER}
    for pipelinePhase in phases:
        for detail in pipelinePhase.details:
            storyId = _assignStoryPhase(detail)
            grouped[storyId].append(detail)

    storyPhases: list[StoryPhaseView] = []
    for phaseId, title in STORY_PHASE_ORDER:
        details = grouped[phaseId]
        evidenceIds: list[str] = []
        gateDecision = ""
        for detail in details:
            for logId in detail.evidence_log_ids:
                if logId not in evidenceIds:
                    evidenceIds.append(logId)
            if detail.decision and not gateDecision:
                gateDecision = detail.decision.replace("_", " ")
        status = "complete" if details else "pending"
        storyPhases.append(
            StoryPhaseView(
                phase_id=phaseId,
                title=title,
                status=status,
                description=_humanPhaseDescription(phaseId, details),
                evidence_log_ids=evidenceIds,
                gate_decision=gateDecision,
            )
        )
    return storyPhases


def buildIncidentStory(
    metadata: IncidentMetadata,
    diagnosis: InvestigationResult,
    hydratedLogs: list[HydratedLogEntry],
    phases: list[PipelinePhase],
    causalChain: list[CausalChainNode],
    integrityVerified: bool,
) -> IncidentStory:
    validateDetails: list[TraceStepDetail] = []
    for pipelinePhase in phases:
        for detail in pipelinePhase.details:
            if _assignStoryPhase(detail) == "validate":
                validateDetails.append(detail)

    categoryValue = diagnosis.root_cause_category.value
    storyPhases = buildStoryPhases(phases)
    mechanismChain = buildEvidenceMechanismChain(diagnosis, hydratedLogs)
    confidence = _extractConfidence(validateDetails)
    failureTitle = buildFailureTitle(diagnosis)
    whyBrief = buildWhyBrief(diagnosis, metadata, hydratedLogs)
    whyFailed = buildWhyItFailed(diagnosis, metadata, hydratedLogs)

    story = IncidentStory(
        incident_title=buildIncidentTitle(metadata, diagnosis),
        failure_title=failureTitle,
        headline=failureTitle,
        why_brief=whyBrief,
        why_it_failed=whyFailed,
        divergence_step=diagnosis.divergence_step,
        divergence_step_label=humanizeStep(diagnosis.divergence_step),
        root_cause_category=categoryValue,
        root_cause_label=humanizeCategory(categoryValue),
        root_cause_description=describeCategory(categoryValue),
        evidence_log_ids=list(diagnosis.evidence_log_ids),
        culprit_log_ids=list(diagnosis.culprit_log_ids),
        confidence=confidence,
        confidence_label=buildConfidenceLabel(confidence),
        integrity_verified=integrityVerified,
        process_steps=buildProcessSteps(metadata, diagnosis),
        key_evidence_log_ids=selectKeyEvidenceIds(diagnosis),
        story_phases=storyPhases,
        mechanism_chain=mechanismChain,
        causal_chain_nodes=causalChain,
        incident_summary="",
    )
    story.incident_summary = buildIncidentSummary(story)
    return story
