"""Evidence-Grounded Post-Mortem Reporter — formats immutable baseline diagnosis."""

from __future__ import annotations

import json
import re
from typing import Protocol

from agents.log_lookup import LogLookupTool
from shared.llm import LlmCallResult
from shared.schemas import (
    EvalCase,
    EvidenceClaimTrace,
    InvestigationResult,
    LogEntry,
    PostMortemArtifact,
    PostMortemReport,
)
from shared.trajectories import TrajectoryLogger

POST_MORTEM_REPORTER_INSTRUCTIONS = """You are an Evidence-Grounded Post-Mortem Reporter.

Your job is to turn a validated forensic diagnosis into a production-quality Markdown
incident post-mortem for engineering and operations stakeholders.

AUTHORITY MODEL:
- The InvestigationResult diagnosis is the diagnostic authority.
- These fields are IMMUTABLE — report them exactly, do not reinterpret or replace:
  divergence_step, root_cause_category, culprit_log_ids
- You may explain and format the diagnosis, but must NOT change it.
- If you believe the diagnosis is questionable, note that only under
  "Confidence & Limitations". Never substitute an alternate diagnosis.

INPUT YOU RECEIVE:
1. Process context (process name, expected sequence)
2. Immutable diagnosis (InvestigationResult)
3. Raw log records retrieved via fetch_log_details for every cited evidence/culprit log

EVIDENCE RULES:
- Every factual claim about the incident must be grounded in retrieved logs or the
  immutable diagnosis.
- Do not invent log IDs, timestamps, services, messages, or metadata.
- Cite log IDs (e.g. c01-02) when referencing specific evidence in narrative sections.
- Do not claim logs were retrieved if they were not supplied.
- Do not use hedging words (likely, probably, presumably) unless the diagnosis explicitly contains them.
- Do not claim business or revenue impact (lost sale, revenue loss, churn, negative UX at scale)
  unless a retrieved log message explicitly states it.
- When broader business or customer impact is unknown, state that explicitly in Impact.
- Do not strengthen causal claims beyond diagnosis.explanation and cited log messages.
- Distinguish clearly: divergence_step = WHERE the process diverged; root_cause_category = WHY category;
  log messages = WHAT the evidence shows. Do not treat a single log message as the root cause unless
  diagnosis.culprit_log_ids and explanation support that framing.
- Executive Summary must not repeat the full causal chain — state divergence, category, and impact
  in 2–4 sentences without inventing upstream causes not in the diagnosis or logs.

Write like an SRE incident report — concise, factual, no repetition across sections.
The UI already shows the diagnosis summary; provide depth here without duplicating every sentence.

Write a Markdown document with EXACTLY these section headings (level-2 ## headers):
1. Executive Summary
2. What Happened
3. Incident Timeline
4. Root Cause
5. Detected Divergence
6. Causal Chain
7. Impact
8. Recommended Remediation
9. Confidence & Limitations

Do NOT include Evidence or Evidence Trace sections — those are appended
deterministically after your narrative.

Return JSON:
{
  "markdown": "<full markdown post-mortem narrative>"
}
"""

REQUIRED_POST_MORTEM_SECTIONS = (
    "Executive Summary",
    "What Happened",
    "Incident Timeline",
    "Root Cause",
    "Detected Divergence",
    "Causal Chain",
    "Impact",
    "Recommended Remediation",
    "Confidence & Limitations",
)

LOG_ID_PATTERN = re.compile(r"\b(c\d{2}-\d{2})\b")


class LlmJsonClient(Protocol):
    def completeJson(
        self,
        prompt: str,
        modelClass: type[PostMortemReport],
        stage: str = "unknown",
    ) -> LlmCallResult: ...


def assertDiagnosisUnchanged(
    original: InvestigationResult,
    preserved: InvestigationResult,
) -> None:
    if original.divergence_step != preserved.divergence_step:
        raise ValueError("Reporter altered divergence_step")
    if original.root_cause_category != preserved.root_cause_category:
        raise ValueError("Reporter altered root_cause_category")
    if original.culprit_log_ids != preserved.culprit_log_ids:
        raise ValueError("Reporter altered culprit_log_ids")


def assertRequiredPostMortemSections(markdown: str) -> None:
    missing = [section for section in REQUIRED_POST_MORTEM_SECTIONS if section not in markdown]
    if missing:
        raise ValueError(f"Post-mortem missing required sections: {missing}")


def extractCitedLogIds(markdown: str) -> set[str]:
    return set(LOG_ID_PATTERN.findall(markdown))


def assertEvidenceGrounding(
    markdown: str,
    allowedLogIds: set[str],
) -> None:
    cited = extractCitedLogIds(markdown)
    ungrounded = cited - allowedLogIds
    if ungrounded:
        raise ValueError(
            f"Post-mortem cites log IDs not hydrated by fetch_log_details: {sorted(ungrounded)}"
        )


def serializeLogBlock(logId: str, log: LogEntry) -> str:
    payload = log.model_dump(mode="json")
    return f"--- fetch_log_details({logId!r}) ---\n{json.dumps(payload, indent=2)}"


def retrieveEvidenceLogs(
    tool: LogLookupTool,
    evidenceLogIds: list[str],
) -> tuple[dict[str, LogEntry], list[str]]:
    return tool.fetchMany(evidenceLogIds)


def retrieveCulpritLogs(
    tool: LogLookupTool,
    culpritLogIds: list[str],
) -> tuple[dict[str, LogEntry], list[str]]:
    return tool.fetchMany(culpritLogIds)


def hydrateDiagnosisLogs(
    case: EvalCase,
    diagnosis: InvestigationResult,
) -> tuple[dict[str, LogEntry], dict[str, LogEntry], list[str]]:
    tool = LogLookupTool(case.raw_logs)
    evidenceLogs, unknownEvidence = retrieveEvidenceLogs(tool, diagnosis.evidence_log_ids)
    culpritLogs, unknownCulprits = retrieveCulpritLogs(tool, diagnosis.culprit_log_ids)
    for logId, log in evidenceLogs.items():
        culpritLogs.setdefault(logId, log)
    unknownLogIds = list(dict.fromkeys(unknownEvidence + unknownCulprits))
    return evidenceLogs, culpritLogs, unknownLogIds


def logRole(logId: str, diagnosis: InvestigationResult) -> str:
    isCulprit = logId in diagnosis.culprit_log_ids
    isEvidence = logId in diagnosis.evidence_log_ids
    if isCulprit and isEvidence:
        return "culprit + evidence"
    if isCulprit:
        return "culprit"
    if isEvidence:
        return "evidence"
    return "supporting"


def buildEvidenceTableMarkdown(
    diagnosis: InvestigationResult,
    hydratedLogs: dict[str, LogEntry],
) -> str:
    orderedIds = list(dict.fromkeys(diagnosis.evidence_log_ids + diagnosis.culprit_log_ids))
    lines = [
        "## Evidence",
        "",
        "| Log ID | Timestamp | Service | Message | Role |",
        "|--------|-----------|---------|---------|------|",
    ]
    for logId in orderedIds:
        if logId not in hydratedLogs:
            lines.append(f"| {logId} | — | — | *(not retrieved)* | {logRole(logId, diagnosis)} |")
            continue
        log = hydratedLogs[logId]
        message = log.message.replace("|", "\\|")
        lines.append(
            f"| {logId} | {log.timestamp} | {log.service} | {message} | {logRole(logId, diagnosis)} |"
        )
    return "\n".join(lines)


def buildClaimTraces(
    diagnosis: InvestigationResult,
    hydratedLogs: dict[str, LogEntry],
) -> list[EvidenceClaimTrace]:
    traces: list[EvidenceClaimTrace] = [
        EvidenceClaimTrace(
            claim=f"Process diverged at step '{diagnosis.divergence_step}'",
            supporting_log_ids=list(diagnosis.culprit_log_ids),
            source="diagnosis",
        ),
        EvidenceClaimTrace(
            claim=f"Root cause category is '{diagnosis.root_cause_category.value}'",
            supporting_log_ids=list(diagnosis.evidence_log_ids),
            source="diagnosis",
        ),
    ]
    if diagnosis.explanation.strip():
        explanationIds = [
            logId for logId in diagnosis.evidence_log_ids if logId in diagnosis.explanation
        ]
        if not explanationIds:
            explanationIds = list(diagnosis.evidence_log_ids)
        traces.append(
            EvidenceClaimTrace(
                claim=f"Diagnostic explanation: {diagnosis.explanation.strip()}",
                supporting_log_ids=explanationIds,
                source="diagnosis",
            )
        )
    for logId in diagnosis.culprit_log_ids:
        if logId not in hydratedLogs:
            continue
        log = hydratedLogs[logId]
        traces.append(
            EvidenceClaimTrace(
                claim=f"Culprit anchor — {log.service}: {log.message}",
                supporting_log_ids=[logId],
                source="diagnosis",
            )
        )
    for logId in diagnosis.evidence_log_ids:
        if logId in diagnosis.culprit_log_ids or logId not in hydratedLogs:
            continue
        log = hydratedLogs[logId]
        traces.append(
            EvidenceClaimTrace(
                claim=f"Supporting evidence — {log.service}: {log.message}",
                supporting_log_ids=[logId],
                source="diagnosis",
            )
        )
    return traces


def buildClaimTraceMarkdown(claimTraces: list[EvidenceClaimTrace]) -> str:
    lines = ["## Evidence Trace", ""]
    for index, trace in enumerate(claimTraces, start=1):
        logList = ", ".join(trace.supporting_log_ids) if trace.supporting_log_ids else "(none)"
        lines.append(f"{index}. **Claim:** {trace.claim}")
        lines.append(f"   - **Supporting logs:** {logList}")
        lines.append(f"   - **Source:** {trace.source}")
        lines.append("")
    return "\n".join(lines).rstrip()


def assembleFullReport(
    narrativeMarkdown: str,
    evidenceTableMarkdown: str,
    claimTraceMarkdown: str,
    diagnosis: InvestigationResult,
    caseId: str = "",
) -> str:
    caseLine = f"**Case ID:** `{caseId}`  \n" if caseId else ""
    header = (
        f"# Incident Post-Mortem\n\n"
        f"{caseLine}"
        f"**Divergence step:** `{diagnosis.divergence_step}`  \n"
        f"**Root cause category:** `{diagnosis.root_cause_category.value}`  \n"
        f"**Culprit logs:** {', '.join(diagnosis.culprit_log_ids) or '(none)'}\n"
    )
    body = narrativeMarkdown.strip()
    if not body.startswith("#"):
        body = header + "\n" + body
    else:
        body = header + "\n" + body
    return f"{body}\n\n{evidenceTableMarkdown}\n\n{claimTraceMarkdown}\n"


def buildPostMortemPrompt(
    case: EvalCase,
    diagnosis: InvestigationResult,
    evidenceLogs: dict[str, LogEntry],
    culpritLogs: dict[str, LogEntry],
    unknownLogIds: list[str],
) -> str:
    processBlock = json.dumps(case.process_context.model_dump(mode="json"), indent=2)
    diagnosisBlock = diagnosis.model_dump_json(indent=2)
    allLogs = dict(evidenceLogs)
    allLogs.update(culpritLogs)
    orderedIds = list(dict.fromkeys(diagnosis.evidence_log_ids + diagnosis.culprit_log_ids))
    logBlocks = [
        serializeLogBlock(logId, allLogs[logId])
        for logId in orderedIds
        if logId in allLogs
    ]
    unknownBlock = ""
    if unknownLogIds:
        unknownBlock = (
            "\nUNKNOWN LOG IDS (fetch_log_details rejected these diagnosis references):\n"
            + json.dumps(unknownLogIds, indent=2)
            + "\n"
        )
    return (
        f"{POST_MORTEM_REPORTER_INSTRUCTIONS}\n\n"
        f"CASE ID: {case.case_id}\n\n"
        f"PROCESS CONTEXT:\n{processBlock}\n\n"
        f"IMMUTABLE DIAGNOSIS (InvestigationResult — do not alter):\n{diagnosisBlock}\n\n"
        f"HYDRATED LOGS (via fetch_log_details):\n"
        + ("\n".join(logBlocks) if logBlocks else "(none retrieved)\n")
        + unknownBlock
    )


def runPostMortemReporter(
    case: EvalCase,
    diagnosis: InvestigationResult,
    client: LlmJsonClient,
    trajectory: TrajectoryLogger | None = None,
    investigationStage: int | None = None,
) -> PostMortemArtifact:
    immutableDiagnosis = InvestigationResult.model_validate(diagnosis.model_dump(mode="json"))
    evidenceLogs, culpritLogs, unknownLogIds = hydrateDiagnosisLogs(case, immutableDiagnosis)
    hydratedLogs = dict(evidenceLogs)
    hydratedLogs.update(culpritLogs)
    allowedLogIds = set(hydratedLogs.keys())

    if trajectory:
        trajectory.log(
            agent="post_mortem_reporter",
            event="logs_retrieved",
            instructions=POST_MORTEM_REPORTER_INSTRUCTIONS,
            inputPayload={
                "case_id": case.case_id,
                "evidence_log_ids": immutableDiagnosis.evidence_log_ids,
                "culprit_log_ids": immutableDiagnosis.culprit_log_ids,
            },
            outputPayload={
                "retrieved_evidence": list(evidenceLogs.keys()),
                "retrieved_culprits": list(culpritLogs.keys()),
                "unknown_log_ids": unknownLogIds,
            },
        )

    prompt = buildPostMortemPrompt(
        case,
        immutableDiagnosis,
        evidenceLogs,
        culpritLogs,
        unknownLogIds,
    )
    if trajectory:
        trajectory.log(
            agent="post_mortem_reporter",
            event="prompt_built",
            inputPayload={"prompt_length": len(prompt)},
        )

    reportMarkdown = ""
    retryFeedback = ""
    callResult = None
    for attempt in range(3):
        attemptPrompt = prompt if not retryFeedback else f"{prompt}\n\nRETRY FEEDBACK:\n{retryFeedback}\n"
        callResult = client.completeJson(attemptPrompt, PostMortemReport, stage="post_mortem_reporter")
        candidate = PostMortemReport.model_validate(callResult.parsed.model_dump())
        try:
            assertRequiredPostMortemSections(candidate.markdown)
            assertEvidenceGrounding(candidate.markdown, allowedLogIds)
            reportMarkdown = candidate.markdown
            break
        except ValueError as error:
            retryFeedback = str(error)
            if attempt == 2:
                raise
    assert callResult is not None
    report = PostMortemReport(markdown=reportMarkdown)

    claimTraces = buildClaimTraces(immutableDiagnosis, hydratedLogs)
    evidenceTableMarkdown = buildEvidenceTableMarkdown(immutableDiagnosis, hydratedLogs)
    claimTraceMarkdown = buildClaimTraceMarkdown(claimTraces)
    fullMarkdown = assembleFullReport(
        report.markdown,
        evidenceTableMarkdown,
        claimTraceMarkdown,
        immutableDiagnosis,
        caseId=case.case_id,
    )
    assertEvidenceGrounding(fullMarkdown, allowedLogIds)

    artifact = PostMortemArtifact(
        case_id=case.case_id,
        diagnosis=immutableDiagnosis,
        markdown=fullMarkdown,
        retrieved_evidence_log_ids=list(evidenceLogs.keys()),
        retrieved_culprit_log_ids=list(culpritLogs.keys()),
        unknown_log_ids=unknownLogIds,
        claim_traces=claimTraces,
        evidence_table_markdown=evidenceTableMarkdown,
        investigation_stage=investigationStage,
    )
    assertDiagnosisUnchanged(immutableDiagnosis, artifact.diagnosis)

    if trajectory:
        trajectory.log(
            agent="post_mortem_reporter",
            event="report_generated",
            outputPayload={
                "markdown_length": len(fullMarkdown),
                "sections_present": list(REQUIRED_POST_MORTEM_SECTIONS),
                "claim_trace_count": len(claimTraces),
            },
            retryCount=callResult.retry_count,
        )
    return artifact
