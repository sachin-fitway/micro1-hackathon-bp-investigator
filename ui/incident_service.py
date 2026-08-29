"""Orchestrates the incident pipeline for the UI layer."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from agents.post_mortem_reporter import (
    assertDiagnosisUnchanged,
    hydrateDiagnosisLogs,
    logRole,
    runPostMortemReporter,
)
from shared.case_loader import BENCHMARK_CASE_IDS, CASES_DIR, loadCase
from shared.llm import GeminiClient
from shared.schemas import EvalCase, InvestigationResult, LlmEvalCase, LogEntry, ProcessContext
from shared.trajectories import TrajectoryLogger, TRAJECTORIES_DIR
from ui.models import (
    BenchmarkCaseSummary,
    CausalChainNode,
    DemoCaseSummary,
    HydratedLogEntry,
    IncidentInvestigationResponse,
    IncidentMetadata,
)
from ui.trace_parser import buildPipelinePhases
from ui.story_formatter import buildIncidentStory
from agents.main_agent import runWorkflowFull

FEATURED_CASE_IDS = frozenset({"case_01", "case_11", "case_14", "case_15"})
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "artifacts"

# Backward-compatible exports used by health checks and scripts.
DEMO_CASE_IDS = BENCHMARK_CASE_IDS


def formatProcessLabel(processName: str) -> str:
    return processName.replace("_", " ")


def listBenchmarkCases() -> list[BenchmarkCaseSummary]:
    return [buildCasePreview(caseId) for caseId in BENCHMARK_CASE_IDS]


def listDemoCases() -> list[BenchmarkCaseSummary]:
    return listBenchmarkCases()


def buildCaseMetadata(case: EvalCase) -> IncidentMetadata:
    relevantLogs = [log for log in case.raw_logs if not log.metadata.get("irrelevant")]
    correlationIds = sorted(
        {
            str(log.metadata.get("correlation_id", "—"))
            for log in relevantLogs
            if log.metadata.get("correlation_id")
        }
    )
    return IncidentMetadata(
        case_id=case.case_id,
        process_name=case.process_context.process_name,
        expected_sequence=list(case.process_context.expected_sequence),
        log_count=len(case.raw_logs),
        correlation_ids=correlationIds,
        noise_log_count=len(case.raw_logs) - len(relevantLogs),
    )


def buildCasePreview(caseId: str) -> BenchmarkCaseSummary:
    case = loadCase(CASES_DIR / f"{caseId}.json")
    metadata = buildCaseMetadata(case)
    caseNumber = int(caseId.split("_")[1])
    artifactPath = ARTIFACTS_DIR / f"{caseId}_post_mortem.json"
    return BenchmarkCaseSummary(
        case_id=metadata.case_id,
        case_number=caseNumber,
        process_name=metadata.process_name,
        process_label=formatProcessLabel(metadata.process_name),
        expected_sequence=metadata.expected_sequence,
        log_count=metadata.log_count,
        correlation_ids=metadata.correlation_ids,
        is_featured=caseId in FEATURED_CASE_IDS,
        has_stored_artifact=artifactPath.exists(),
    )


def parseIncidentPayload(payload: dict) -> EvalCase:
    if "ground_truth" in payload or "meta" in payload:
        return EvalCase.model_validate(payload)
    llmCase = LlmEvalCase.model_validate(payload)
    if not llmCase.process_context.expected_sequence:
        raise ValueError("expected_sequence is required in process_context")
    if not llmCase.raw_logs:
        raise ValueError("raw_logs must not be empty")
    caseId = llmCase.case_id or f"incident_{uuid.uuid4().hex[:8]}"
    return EvalCase(
        case_id=caseId,
        process_context=llmCase.process_context,
        raw_logs=llmCase.raw_logs,
        ground_truth=_placeholderGroundTruth(caseId, llmCase.process_context),
        meta=_placeholderMeta(),
    )


def _placeholderGroundTruth(caseId: str, processContext: ProcessContext):
    from shared.schemas import GroundTruth, RootCauseCategory

    step = processContext.expected_sequence[0] if processContext.expected_sequence else "unknown"
    return GroundTruth(
        divergence_step=step,
        root_cause_category=RootCauseCategory.CONFIG_DRIFT,
        culprit_log_ids=[],
        required_evidence_ids=[],
    )


def _placeholderMeta():
    from shared.schemas import CaseMeta, DifficultyFactors

    return CaseMeta(
        failure_pattern="user_upload",
        difficulty="standard",
        baseline_hypothesis="either",
        domain="b2b_saas",
        difficulty_factors=DifficultyFactors(
            log_noise=0,
            causal_distance=0,
            competing_hypotheses=0,
            evidence_dispersion=0,
            metadata_conflict=0,
            temporal_ambiguity=0,
        ),
    )


def buildCausalChain(
    case: EvalCase,
    diagnosis: InvestigationResult,
) -> list[CausalChainNode]:
    sequence = case.process_context.expected_sequence
    divergenceIndex = next(
        (index for index, step in enumerate(sequence) if step == diagnosis.divergence_step),
        -1,
    )
    nodes: list[CausalChainNode] = []
    for index, step in enumerate(sequence):
        kind = "step"
        label = step.replace("_", " ")
        logIds: list[str] = []
        if index == divergenceIndex:
            kind = "failure"
            label = f"Divergence: {step}"
            logIds = list(diagnosis.culprit_log_ids)
        elif index > divergenceIndex >= 0:
            kind = "consequence"
            label = f"Downstream: {step}"
            logIds = [
                logId
                for logId in diagnosis.evidence_log_ids
                if logId not in diagnosis.culprit_log_ids
            ]
        nodes.append(
            CausalChainNode(
                step=step,
                kind=kind,
                label=label,
                supporting_log_ids=logIds,
                is_divergence=index == divergenceIndex,
            )
        )
    return nodes


def buildHydratedLogEntries(
    case: EvalCase,
    diagnosis: InvestigationResult,
) -> list[HydratedLogEntry]:
    evidenceLogs, culpritLogs, unknown = hydrateDiagnosisLogs(case, diagnosis)
    hydrated = dict(evidenceLogs)
    hydrated.update(culpritLogs)
    orderedIds = list(dict.fromkeys(diagnosis.evidence_log_ids + diagnosis.culprit_log_ids))
    entries: list[HydratedLogEntry] = []
    for logId in orderedIds:
        if logId not in hydrated:
            continue
        log = hydrated[logId]
        entries.append(
            HydratedLogEntry(
                log_id=log.log_id,
                timestamp=log.timestamp,
                service=log.service,
                message=log.message,
                metadata=dict(log.metadata),
                role=logRole(logId, diagnosis),
            )
        )
    for log in sorted(case.raw_logs, key=lambda entry: entry.timestamp):
        if log.metadata.get("irrelevant"):
            continue
        if log.log_id in hydrated:
            continue
        entries.append(
            HydratedLogEntry(
                log_id=log.log_id,
                timestamp=log.timestamp,
                service=log.service,
                message=log.message,
                metadata=dict(log.metadata),
                role="context",
            )
        )
    return entries


def runIncidentInvestigation(
    case: EvalCase,
    client: GeminiClient,
    investigationStage: int = 3,
) -> IncidentInvestigationResponse:
    immutableBefore = None
    metadata = buildCaseMetadata(case)

    investigationTrajectory = TrajectoryLogger(case.case_id, stage=str(investigationStage))
    if investigationStage != 3:
        from workflows.ablation import STAGE_RUNNERS

        diagnosis = STAGE_RUNNERS[investigationStage](case, client)
    else:
        diagnosis = runWorkflowFull(case, client, trajectory=investigationTrajectory)
    immutableBefore = InvestigationResult.model_validate(diagnosis.model_dump(mode="json"))

    postMortemTrajectory = TrajectoryLogger(case.case_id, stage="post_mortem")
    artifact = runPostMortemReporter(
        case,
        diagnosis,
        client,
        trajectory=postMortemTrajectory,
        investigationStage=investigationStage,
    )
    assertDiagnosisUnchanged(immutableBefore, artifact.diagnosis)

    phases = buildPipelinePhases(
        investigationTrajectory.file_path,
        postMortemTrajectory.file_path,
    )
    hydratedLogs = buildHydratedLogEntries(case, artifact.diagnosis)
    causalChain = buildCausalChain(case, artifact.diagnosis)
    story = buildIncidentStory(
        metadata,
        artifact.diagnosis,
        hydratedLogs,
        phases,
        causalChain,
        integrityVerified=True,
    )

    return IncidentInvestigationResponse(
        case_id=case.case_id,
        metadata=metadata,
        diagnosis=artifact.diagnosis,
        diagnosis_integrity_verified=True,
        story=story,
        phases=phases,
        hydrated_logs=hydratedLogs,
        claim_traces=artifact.claim_traces,
        causal_chain=causalChain,
        post_mortem_markdown=artifact.markdown,
        post_mortem_artifact=artifact,
        evidence_table_markdown=artifact.evidence_table_markdown,
        unknown_log_ids=artifact.unknown_log_ids,
        investigation_stage=investigationStage,
    )


def loadCaseFromBenchmark(caseId: str) -> EvalCase:
    if ".." in caseId or "/" in caseId or "\\" in caseId:
        raise FileNotFoundError(f"Unknown benchmark case: {caseId}")
    path = (CASES_DIR / f"{caseId}.json").resolve()
    casesRoot = CASES_DIR.resolve()
    if not path.is_relative_to(casesRoot):
        raise FileNotFoundError(f"Unknown benchmark case: {caseId}")
    if not path.exists():
        raise FileNotFoundError(f"Unknown benchmark case: {caseId}")
    return loadCase(path)


def loadArtifactDiagnosis(caseId: str, artifactsDir: Path | None = None) -> InvestigationResult:
    directory = artifactsDir or Path(__file__).resolve().parent.parent / "reports" / "artifacts"
    path = directory / f"{caseId}_post_mortem.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return InvestigationResult.model_validate(payload["diagnosis"])
