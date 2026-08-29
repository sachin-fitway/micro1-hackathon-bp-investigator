"""Pydantic schemas for benchmark cases and investigation results."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RootCauseCategory(str, Enum):
    SEQUENCE_SKIP = "sequence_skip"
    TIMEOUT_STALL = "timeout_stall"
    RACE_CONDITION = "race_condition"
    WEBHOOK_MISSING = "webhook_missing"
    FALSE_SUCCESS_SIGNAL = "false_success_signal"
    METADATA_MESSAGE_CONFLICT = "metadata_message_conflict"
    DOWNSTREAM_MASKS_UPSTREAM = "downstream_masks_upstream"
    DUPLICATE_PROCESSING = "duplicate_processing"
    ENTITLEMENT_MISMATCH = "entitlement_mismatch"
    CONFIG_DRIFT = "config_drift"


class LogEntry(BaseModel):
    log_id: str
    timestamp: str
    service: str
    message: str
    metadata: dict = Field(default_factory=dict)


class ProcessContext(BaseModel):
    process_name: str
    expected_sequence: list[str]


class DecoyDiagnosis(BaseModel):
    """Plausible wrong answer stored for analysis — never shown to LLM."""

    decoy_type: str
    divergence_step: str
    root_cause_category: RootCauseCategory
    culprit_log_ids: list[str]
    decoy_evidence_ids: list[str]


class GroundTruth(BaseModel):
    divergence_step: str
    root_cause_category: RootCauseCategory
    culprit_log_ids: list[str]
    required_evidence_ids: list[str]
    decoy_diagnosis: DecoyDiagnosis | None = None
    acceptable_root_causes: list[RootCauseCategory] = Field(default_factory=list)


class DifficultyFactors(BaseModel):
    """Independent complexity signals for post-hoc analysis — never used in scoring or LLM input."""

    log_noise: int = Field(ge=0, le=3)
    causal_distance: int = Field(ge=0, le=3)
    competing_hypotheses: int = Field(ge=0, le=3)
    evidence_dispersion: int = Field(ge=0, le=3)
    metadata_conflict: int = Field(ge=0, le=3)
    temporal_ambiguity: int = Field(ge=0, le=3)

    @property
    def composite_score(self) -> int:
        return (
            self.log_noise
            + self.causal_distance
            + self.competing_hypotheses
            + self.evidence_dispersion
            + self.metadata_conflict
            + self.temporal_ambiguity
        )


class CaseMeta(BaseModel):
    """Post-evaluation analysis metadata. NEVER passed to LLM. NEVER used in scoring."""

    failure_pattern: str
    difficulty: Literal["standard", "hard"]
    baseline_hypothesis: Literal["baseline", "agent", "either"]
    domain: Literal["ecommerce", "fintech", "b2b_saas"]
    difficulty_factors: DifficultyFactors

    @field_validator("baseline_hypothesis", mode="before")
    @classmethod
    def migrateExpectedWinner(cls, value: str) -> str:
        if value == "expected_winner":
            raise ValueError("Use baseline_hypothesis instead of expected_winner")
        return value


class EvalCase(BaseModel):
    case_id: str
    process_context: ProcessContext
    raw_logs: list[LogEntry]
    ground_truth: GroundTruth
    meta: CaseMeta


ROOT_CAUSE_ALIASES: dict[str, RootCauseCategory] = {
    "configuration_error": RootCauseCategory.CONFIG_DRIFT,
    "config_error": RootCauseCategory.CONFIG_DRIFT,
    "network_issue": RootCauseCategory.TIMEOUT_STALL,
    "external_dependency_failure": RootCauseCategory.WEBHOOK_MISSING,
}


def coerceRootCauseCategory(value: str | RootCauseCategory) -> RootCauseCategory:
    if isinstance(value, RootCauseCategory):
        return value
    normalized = str(value).strip().lower()
    if normalized in ROOT_CAUSE_ALIASES:
        return ROOT_CAUSE_ALIASES[normalized]
    try:
        return RootCauseCategory(normalized)
    except ValueError:
        return RootCauseCategory.CONFIG_DRIFT


class InvestigationResult(BaseModel):
    divergence_step: str
    root_cause_category: RootCauseCategory
    culprit_log_ids: list[str]
    evidence_log_ids: list[str]
    explanation: str = ""

    @field_validator("root_cause_category", mode="before")
    @classmethod
    def normalizeRootCauseCategory(cls, value: str | RootCauseCategory) -> RootCauseCategory:
        return coerceRootCauseCategory(value)


class PostMortemReport(BaseModel):
    """Markdown incident post-mortem produced by the reporter agent."""

    markdown: str = Field(min_length=1)


class EvidenceClaimTrace(BaseModel):
    """Maps a major post-mortem claim to supporting log IDs."""

    claim: str = Field(min_length=1)
    supporting_log_ids: list[str] = Field(default_factory=list)
    source: Literal["diagnosis", "report"] = "diagnosis"


class PostMortemArtifact(BaseModel):
    """Reporter output — preserves the immutable baseline diagnosis."""

    case_id: str
    diagnosis: InvestigationResult
    markdown: str
    retrieved_evidence_log_ids: list[str]
    retrieved_culprit_log_ids: list[str]
    unknown_log_ids: list[str] = Field(default_factory=list)
    claim_traces: list[EvidenceClaimTrace] = Field(default_factory=list)
    evidence_table_markdown: str = ""
    investigation_stage: int | None = None


HypothesisSource = Literal["baseline", "rule_checker", "decoy_trap"]


class HypothesisCandidate(BaseModel):
    hypothesis_id: str
    source: HypothesisSource
    divergence_step: str
    root_cause_category: RootCauseCategory
    culprit_log_ids: list[str]
    evidence_log_ids: list[str]
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    earlier_explanation: str = ""
    explanation: str = ""

    @field_validator("root_cause_category", mode="before")
    @classmethod
    def normalizeRootCauseCategory(cls, value: str | RootCauseCategory) -> RootCauseCategory:
        return coerceRootCauseCategory(value)

    @field_validator("source", mode="before")
    @classmethod
    def normalizeSource(cls, value: str) -> str:
        if value == "decoy_trap":
            return "decoy_trap"
        return value


class HypothesisBoard(BaseModel):
    leading_hypothesis_id: str
    candidates: list[HypothesisCandidate] = Field(min_length=1)

    @field_validator("candidates", mode="before")
    @classmethod
    def coerceCandidates(cls, value: list[object]) -> list[object]:
        import json

        if not isinstance(value, list):
            return value
        coerced: list[object] = []
        for item in value:
            if isinstance(item, str):
                parsed = json.loads(item)
                if isinstance(parsed, dict) and "hypothesis_id" in parsed:
                    coerced.append(parsed)
                continue
            if isinstance(item, dict):
                if "hypothesis_id" in item:
                    coerced.append(item)
                continue
            coerced.append(item)
        return coerced


class AdversarialVerificationOutcome(BaseModel):
    """Legacy shape — prefer VerifierAdjudicationOutcome for Stage 3."""

    leading_rejected: bool
    selected_hypothesis_id: str
    issues: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    result: InvestigationResult


class HypothesisAssessment(BaseModel):
    valid: bool
    problems: list[str] = Field(default_factory=list)


class CausalComparison(BaseModel):
    baseline_causal_chain: list[str] = Field(default_factory=list)
    challenger_causal_chain: list[str] = Field(default_factory=list)
    why_selected: str = ""


class VerifierAdjudicationOutcome(BaseModel):
    decision: Literal["keep_baseline", "override_baseline"]
    selected_hypothesis: InvestigationResult
    baseline_assessment: HypothesisAssessment
    challenger_assessment: HypothesisAssessment
    comparison: CausalComparison
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    deterministic_blocks: list[str] = Field(default_factory=list)


class TimelineGroup(BaseModel):
    entity_id: str
    ordered_logs: list[LogEntry]


class LlmEvalCase(BaseModel):
    """Case payload safe for LLM consumption — no meta, no ground truth."""

    case_id: str
    process_context: ProcessContext
    raw_logs: list[LogEntry]


class ScoreBreakdown(BaseModel):
    failure_point: float
    root_cause: float
    evidence_recall: float
    evidence_precision: float
    no_fabricated: float
    total: float


class VerificationOutcome(BaseModel):
    is_grounded: bool
    issues: list[str] = Field(default_factory=list)
    result: InvestigationResult | None = None
