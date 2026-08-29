"""UI-only response models — do not use for diagnosis/scoring."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.schemas import EvidenceClaimTrace, InvestigationResult, LogEntry, PostMortemArtifact


class BenchmarkCaseSummary(BaseModel):
    case_id: str
    case_number: int
    process_name: str
    process_label: str
    expected_sequence: list[str]
    log_count: int
    correlation_ids: list[str]
    is_featured: bool = False
    has_stored_artifact: bool = False


# Backward-compatible alias for existing imports/tests.
DemoCaseSummary = BenchmarkCaseSummary


class IncidentMetadata(BaseModel):
    case_id: str
    process_name: str
    expected_sequence: list[str]
    log_count: int
    correlation_ids: list[str]
    noise_log_count: int


class TraceStepDetail(BaseModel):
    label: str
    status: str
    summary: str
    agent: str = ""
    event: str = ""
    evidence_log_ids: list[str] = Field(default_factory=list)
    decision: str = ""
    gate_blocks: list[str] = Field(default_factory=list)


class PipelinePhase(BaseModel):
    phase_id: str
    title: str
    status: str
    details: list[TraceStepDetail] = Field(default_factory=list)


class HydratedLogEntry(BaseModel):
    log_id: str
    timestamp: str
    service: str
    message: str
    metadata: dict = Field(default_factory=dict)
    role: str


class CausalChainNode(BaseModel):
    step: str
    kind: str
    label: str
    supporting_log_ids: list[str] = Field(default_factory=list)
    is_divergence: bool = False


class ProcessStepView(BaseModel):
    step: str
    label: str
    state: str
    culprit_log_ids: list[str] = Field(default_factory=list)


class StoryPhaseView(BaseModel):
    phase_id: str
    title: str
    status: str
    description: str
    evidence_log_ids: list[str] = Field(default_factory=list)
    gate_decision: str = ""


class MechanismChainNode(BaseModel):
    label: str
    log_id: str
    kind: str
    service: str = ""


class IncidentStory(BaseModel):
    incident_title: str
    failure_title: str
    headline: str
    why_brief: str
    why_it_failed: str
    divergence_step: str
    divergence_step_label: str
    root_cause_category: str
    root_cause_label: str
    root_cause_description: str
    evidence_log_ids: list[str] = Field(default_factory=list)
    culprit_log_ids: list[str] = Field(default_factory=list)
    confidence: str | None = None
    confidence_label: str = "Adjudicated diagnosis"
    integrity_verified: bool = False
    process_steps: list[ProcessStepView] = Field(default_factory=list)
    key_evidence_log_ids: list[str] = Field(default_factory=list)
    story_phases: list[StoryPhaseView] = Field(default_factory=list)
    mechanism_chain: list[MechanismChainNode] = Field(default_factory=list)
    causal_chain_nodes: list[CausalChainNode] = Field(default_factory=list)
    incident_summary: str = ""


class IncidentInvestigationResponse(BaseModel):
    case_id: str
    metadata: IncidentMetadata
    diagnosis: InvestigationResult
    diagnosis_integrity_verified: bool
    story: IncidentStory
    phases: list[PipelinePhase]
    hydrated_logs: list[HydratedLogEntry]
    claim_traces: list[EvidenceClaimTrace]
    causal_chain: list[CausalChainNode]
    post_mortem_markdown: str
    post_mortem_artifact: PostMortemArtifact | None = None
    evidence_table_markdown: str
    unknown_log_ids: list[str] = Field(default_factory=list)
    investigation_stage: int = 3
