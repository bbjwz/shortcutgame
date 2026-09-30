from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Finding(StrictModel):
    finding_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Severity
    evidence: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    remediation: str = ""


class DecisionProposal(StrictModel):
    proposal_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class Risk(StrictModel):
    risk_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    mitigation: str = ""


class PersonaPayload(StrictModel):
    summary: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    decisions: list[DecisionProposal] = Field(default_factory=list)
    accepted_proposal_ids: list[str] = Field(default_factory=list)
    rejected_proposal_ids: list[str] = Field(default_factory=list)
    unresolved_decisions: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    superior_ideas: list[str] = Field(default_factory=list)
    self_corrections: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    verdict: Verdict = Verdict.NOT_APPLICABLE
    confidence: int = Field(ge=0, le=100)


class Usage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)


class VisibleExchange(StrictModel):
    kind: Literal["generate", "repair"] = "generate"
    visible_user_prompt: str
    visible_output: str
    request_id: str | None = None
    resolved_model: str
    usage: Usage = Field(default_factory=Usage)
    input_hash: str = ""
    output_hash: str = ""

    @model_validator(mode="after")
    def populate_hashes(self) -> VisibleExchange:
        if not self.input_hash:
            self.input_hash = hashlib.sha256(self.visible_user_prompt.encode()).hexdigest()
        if not self.output_hash:
            self.output_hash = hashlib.sha256(self.visible_output.encode()).hexdigest()
        return self


class IsolationEvidence(StrictModel):
    """Auditable proof that one inference started without conversation history."""

    invocation_id: str = Field(min_length=1)
    adapter_instance_id: str = Field(min_length=1)
    context_mode: Literal["fresh"] = "fresh"
    prior_conversation_messages: Literal[0] = 0
    provider_session_reused: Literal[False] = False


class CallAttemptTranscript(StrictModel):
    attempt_id: str
    run_id: str
    stage: str
    pass_kind: Literal["independent", "disclosed", "compile"]
    persona: str
    participant_id: str
    transport: str
    underlying_vendor: str
    requested_model: str
    attempt_number: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    outcome: Literal["success", "error"]
    retryable: bool = False
    error: str | None = None
    visible_system_prompt: str
    visible_user_prompt: str
    input_hash: str
    isolation: IsolationEvidence
    exchanges: list[VisibleExchange] = Field(default_factory=list)


class Transcript(StrictModel):
    transcript_id: str
    run_id: str
    stage: str
    pass_kind: Literal["independent", "disclosed", "compile"]
    persona: str
    participant_id: str
    transport: str
    underlying_vendor: str
    requested_model: str
    resolved_model: str
    request_id: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    visible_system_prompt: str
    visible_user_prompt: str
    visible_output: str
    input_hash: str
    output_hash: str
    isolation: IsolationEvidence
    usage: Usage = Field(default_factory=Usage)
    exchanges: list[VisibleExchange] = Field(default_factory=list)


class ArtifactEnvelope(StrictModel):
    schema_version: str = "1.0"
    artifact_id: str
    run_id: str
    stage: str
    pass_kind: Literal["independent", "disclosed"]
    persona: str
    participant_id: str
    transport: str
    underlying_vendor: str
    requested_model: str
    resolved_model: str
    generated_at: datetime = Field(default_factory=utc_now)
    input_hash: str
    isolation: IsolationEvidence
    transcript_path: str
    payload: PersonaPayload


class ArchitectureComponent(StrictModel):
    component_id: str
    name: str
    responsibility: str
    source_proposal_ids: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class MasterPlanPayload(StrictModel):
    summary: str
    accepted_decisions: list[DecisionProposal] = Field(default_factory=list)
    rejected_decisions: list[DecisionProposal] = Field(default_factory=list)
    unresolved_tradeoffs: list[str] = Field(default_factory=list)
    components: list[ArchitectureComponent] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)


class MasterPlan(StrictModel):
    schema_version: str = "1.0"
    master_plan_id: str
    run_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    compiled_by: str = "codex"
    decision_manifest_path: str
    input_hash: str
    payload: MasterPlanPayload


class ArchitectureDecisionRecord(StrictModel):
    adr_id: str
    status: Literal["accepted", "rejected"]
    statement: str
    rationale: str
    requirement_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class AdrLog(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    compiled_by: str = "codex"
    records: list[ArchitectureDecisionRecord] = Field(default_factory=list)


class DecisionSelection(StrictModel):
    conflict_id: str
    selected_proposal_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class DecisionOption(StrictModel):
    proposal_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_artifact_ids: list[str] = Field(default_factory=list)


class DecisionConflict(StrictModel):
    conflict_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: list[DecisionOption] = Field(min_length=1)


class GateException(StrictModel):
    validator_artifact_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    approved_at: datetime


class DecisionManifest(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    status: Literal["pending", "approved", "exception"] = "pending"
    decided_by: str = ""
    decided_at: datetime | None = None
    instructions: list[str] = Field(default_factory=list)
    conflicts: list[DecisionConflict] = Field(default_factory=list)
    selections: list[DecisionSelection] = Field(default_factory=list)
    exceptions: list[GateException] = Field(default_factory=list)

    @field_validator("selections")
    @classmethod
    def unique_conflicts(cls, value: list[DecisionSelection]) -> list[DecisionSelection]:
        ids = [item.conflict_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("decision selections contain duplicate conflict_id values")
        return value

    @model_validator(mode="after")
    def validate_decision_state(self) -> DecisionManifest:
        if self.status == "pending":
            return self
        if not self.decided_by.strip() or self.decided_at is None:
            raise ValueError("completed decision manifest requires decided_by and decided_at")
        known = {conflict.conflict_id: conflict for conflict in self.conflicts}
        selected = {selection.conflict_id: selection for selection in self.selections}
        missing = sorted(set(known) - set(selected))
        unknown = sorted(set(selected) - set(known))
        if missing:
            raise ValueError(f"decision selections missing conflicts: {', '.join(missing)}")
        if unknown:
            raise ValueError(
                f"decision selections reference unknown conflicts: {', '.join(unknown)}"
            )
        for conflict_id, selection in selected.items():
            available = {option.proposal_id for option in known[conflict_id].options}
            invalid = sorted(set(selection.selected_proposal_ids) - available)
            if invalid:
                raise ValueError(
                    f"selection {conflict_id!r} references unavailable proposals: "
                    + ", ".join(invalid)
                )
        if self.status == "exception" and not self.exceptions:
            raise ValueError("exception status requires at least one explicit exception")
        return self


class GateIsolationRecord(StrictModel):
    participant_id: str = Field(min_length=1)
    independent_invocation_id: str = Field(min_length=1)
    disclosed_invocation_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_distinct_invocations(self) -> GateIsolationRecord:
        if self.independent_invocation_id == self.disclosed_invocation_id:
            raise ValueError("validator passes must use distinct fresh-context invocations")
        return self


class GateReport(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    feature: str
    generated_at: datetime = Field(default_factory=utc_now)
    status: Literal["READY", "BLOCKED", "AWAITING_HUMAN"]
    required_participants: list[str]
    ready_participants: list[str] = Field(default_factory=list)
    blocked_participants: list[str] = Field(default_factory=list)
    optional_warnings: list[str] = Field(default_factory=list)
    validator_artifact_ids: list[str] = Field(default_factory=list)
    validator_isolation: list[GateIsolationRecord] = Field(default_factory=list)
    exception_applied: bool = False
    decision_manifest_path: str
    master_plan_path: str | None = None


class RunState(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    feature: str
    phase: Literal[
        "created",
        "planning",
        "critiquing",
        "synthesizing",
        "awaiting_human",
        "compiling",
        "validating",
        "ready",
        "blocked",
        "failed",
    ] = "created"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    context_hash: str
    config_hash: str
    call_count: int = 0
    usage: Usage = Field(default_factory=Usage)
    optional_warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    completed_artifact_ids: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utc_now()


class PersonaDefinition(StrictModel):
    id: str
    focus: str


class PersonaRegistry(StrictModel):
    schema_version: str
    planners: list[PersonaDefinition]
    critics: list[PersonaDefinition]
    gatekeepers: list[PersonaDefinition]

    def get(self, persona_id: str) -> PersonaDefinition:
        for persona in [*self.planners, *self.critics, *self.gatekeepers]:
            if persona.id == persona_id:
                return persona
        raise KeyError(persona_id)


JsonObject = dict[str, Any]
