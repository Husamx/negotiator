"""
Pydantic models for API requests and responses.

These models define the data contracts for the HTTP API exposed by
FastAPI. Where possible, they reuse the domain types from the ORM
models (e.g., enumerations) to ensure consistency across layers.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    EventType,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
    MessageRole,
    TemplateProposalStatus,
    UserTier,
)


class EntityCreate(BaseModel):
    """Request model for creating a new entity in the knowledge graph."""

    type: str = Field(..., description="Type of the entity, e.g., person or organization.")
    name: str = Field(..., description="Human-readable name of the entity.")
    attributes: Optional[dict] = Field(None, description="Arbitrary attributes attached to the entity.")


class EntityUpdate(BaseModel):
    """Request model for updating an existing entity."""

    name: Optional[str] = Field(None, description="New name of the entity.")
    attributes: Optional[dict] = Field(None, description="Updated attributes.")


class EntityOut(BaseModel):
    """Response model for an entity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str
    attributes: Optional[dict] = None


class FactCandidate(BaseModel):
    """Represents a candidate fact extracted during a session (session-only)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_entity_id: int
    key: str
    value: str
    scope: KnowledgeScope
    source_ref: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Request payload for creating a new negotiation session."""

    topic_text: str = Field(..., description="1-2 sentence description of the negotiation topic.")
    counterparty_style: Optional[str] = Field(None, description="Optional style for the counterparty's persona.")
    attached_entity_ids: Optional[List[int]] = Field(None, description="IDs of pre-existing entities to attach to the session.")
    channel: Optional[str] = Field(
        "DM",
        description="Negotiation channel (EMAIL, DM, IN_PERSON_NOTES).",
    )


class CreateSessionResponse(BaseModel):
    """Response payload after creating a session."""

    session_id: int = Field(..., description="Identifier of the newly created session.")
    template_id: str = Field(..., description="ID of the template selected for the session.")
    proposed_entities: List[EntityOut] = Field([], description="List of entities suggested for attachment based on the topic.")
    intake_questions: List[str] = Field([], description="List of minimal intake questions to ask before starting roleplay.")


class PostMessageRequest(BaseModel):
    """Request payload for posting a chat message during a session."""

    content: str = Field(..., description="The user's message content.")
    channel: str = Field("roleplay", description="Channel: 'roleplay' or 'coach_private' (premium only).")
    enable_web_grounding: Optional[bool] = Field(True, description="Whether the server may perform web grounding.")
    web_grounding_trigger: Optional[str] = Field(None, description="How web grounding was triggered: auto or user_requested.")


class PostMessageResponse(BaseModel):
    """Response payload after posting a message."""

    counterparty_message: Optional[str] = Field(None, description="Generated message from the counterparty.")
    coach_panel: Optional[dict] = Field(None, description="Premium coach suggestions, if applicable.")
    grounding_pack: Optional[dict] = Field(None, description="Web grounding context pack, if used.")
    extracted_facts: List[FactCandidate] = Field([], description="Facts extracted from the user's message (session-only).")
    strategy_selection: Optional[dict] = Field(None, description="Latest strategy selection payload, if available.")


class EndSessionResponse(BaseModel):
    """Response payload after ending a session."""

    recap: str = Field(..., description="Descriptive recap of the session for the user.")
    after_action_report: Optional[str] = Field(None, description="Premium: detailed analysis and suggestions.")


class MemoryReviewDecision(BaseModel):
    """Instruction for what to do with a candidate fact during memory review."""

    fact_id: int = Field(..., description="The identifier of the fact.")
    decision: str = Field(..., description="One of 'save_global', 'save_session_only' or 'discard'.")


class MemoryReviewRequest(BaseModel):
    """Request payload for committing facts after session review."""

    decisions: List[MemoryReviewDecision] = Field(..., description="User decisions about each candidate fact.")


class MemoryReviewResponse(BaseModel):
    """Response payload after committing facts from memory review."""

    updated_facts: List[FactCandidate] = Field([], description="List of facts that were saved globally or kept in session scope.")


class ErrorResponse(BaseModel):
    """Standard error response model."""

    detail: str


class SessionMessageOut(BaseModel):
    """Response model for session messages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime
    thread_id: Optional[int] = None


class SessionSummary(BaseModel):
    """Summary metadata for listing sessions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: str
    title: str
    topic_text: Optional[str] = None
    counterparty_style: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None


class SessionDetail(BaseModel):
    """Detailed session view with messages and attached entities."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: str
    title: str
    topic_text: Optional[str] = None
    counterparty_style: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None
    active_thread_id: Optional[int] = None
    root_thread_id: Optional[int] = None
    attached_entities: List[EntityOut] = []
    messages: List[SessionMessageOut] = []


class CaseSnapshotOut(BaseModel):
    """Response model for a case snapshot."""

    model_config = ConfigDict(from_attributes=True)

    session_id: int
    payload: dict
    created_at: datetime
    updated_at: datetime


class CaseSnapshotUpdateRequest(BaseModel):
    """Request to apply JSON patch updates to the case snapshot."""

    patches: List[dict] = Field(..., description="RFC6902 JSON patch operations.")


class IntakeSubmitRequest(BaseModel):
    """Submit intake questions + answers to update the case snapshot."""

    questions: List[str] = Field(default_factory=list)
    answers: dict = Field(default_factory=dict)
    summary: Optional[str] = Field(None, description="Optional prebuilt intake summary.")


class IntakeSubmitResponse(BaseModel):
    """Response after applying intake updates."""

    case_snapshot: CaseSnapshotOut
    strategy_selection: Optional[dict] = None


class StrategySummary(BaseModel):
    """Summary model for listing strategies."""

    strategy_id: str
    name: str
    summary: str
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    revision: Optional[int] = None


class StrategySelectionOut(BaseModel):
    """Latest strategy selection output for a session."""

    model_config = ConfigDict(from_attributes=True)

    selected_strategy_id: str
    selection_payload: dict
    strategy_pack_id: str
    strategy_pack_version: Optional[str] = None
    created_at: datetime


class StrategyExecutionRequest(BaseModel):
    """Execute a strategy with optional inputs."""

    strategy_id: Optional[str] = None
    inputs: dict = Field(default_factory=dict)


class StrategyExecutionOut(BaseModel):
    """Response model for a strategy execution."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    strategy_id: str
    strategy_revision: int
    inputs: dict
    artifacts: List[dict]
    case_patches: List[dict]
    judge_outputs: List[dict]
    trace: dict
    created_at: datetime


class SessionUpdateRequest(BaseModel):
    """Request for updating session metadata."""

    title: Optional[str] = None
    counterparty_style: Optional[str] = None


class SessionAttachRequest(BaseModel):
    """Request for attaching or detaching entities."""

    entity_ids: List[int]


class FactCreate(BaseModel):
    """Request model for creating a fact."""

    subject_entity_id: int
    key: str
    value: str
    value_type: Optional[str] = "str"
    unit: Optional[str] = None
    scope: KnowledgeScope = KnowledgeScope.global_scope
    confidence: Optional[float] = 1.0
    provenance: Optional[dict] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None


class FactUpdate(BaseModel):
    """Request model for updating a fact."""

    key: Optional[str] = None
    value: Optional[str] = None
    value_type: Optional[str] = None
    unit: Optional[str] = None
    scope: Optional[KnowledgeScope] = None
    confidence: Optional[float] = None
    provenance: Optional[dict] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None


class FactOut(BaseModel):
    """Response model for a fact."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    session_id: Optional[int] = None
    subject_entity_id: int
    key: str
    value: str
    value_type: str
    unit: Optional[str] = None
    scope: KnowledgeScope
    confidence: float
    provenance: Optional[dict] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RelationshipCreate(BaseModel):
    """Request model for creating a relationship."""

    src_entity_id: int
    rel_type: str
    dst_entity_id: int
    provenance: Optional[dict] = None


class RelationshipUpdate(BaseModel):
    """Request model for updating a relationship."""

    rel_type: Optional[str] = None
    provenance: Optional[dict] = None


class RelationshipOut(BaseModel):
    """Response model for a relationship."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    src_entity_id: int
    rel_type: str
    dst_entity_id: int
    provenance: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class KnowledgeEdgeCreate(BaseModel):
    """Request model for creating a knowledge edge."""

    knower_entity_id: int
    fact_id: int
    status: KnowledgeStatus
    confidence: Optional[float] = 1.0
    source: KnowledgeSource
    scope: KnowledgeScope = KnowledgeScope.global_scope


class KnowledgeEdgeUpdate(BaseModel):
    """Request model for updating a knowledge edge."""

    status: Optional[KnowledgeStatus] = None
    confidence: Optional[float] = None
    source: Optional[KnowledgeSource] = None
    scope: Optional[KnowledgeScope] = None


class KnowledgeEdgeOut(BaseModel):
    """Response model for a knowledge edge."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    knower_entity_id: int
    fact_id: int
    status: KnowledgeStatus
    confidence: float
    source: KnowledgeSource
    scope: KnowledgeScope
    created_at: datetime
    updated_at: datetime


class TemplateDraftOut(BaseModel):
    """Response model for a template draft."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    topic_text: str
    title: Optional[str] = None
    payload: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class TemplateProposalCreate(BaseModel):
    """Request model for submitting a template proposal."""

    draft_id: Optional[int] = None
    payload: dict


class TemplateProposalOut(BaseModel):
    """Response model for a template proposal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    draft_id: Optional[int] = None
    status: TemplateProposalStatus
    payload: Optional[dict] = None
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class TemplateReviewRequest(BaseModel):
    """Admin review decision for template proposals."""

    decision: str
    reviewer_notes: Optional[str] = None


class UserTierUpdate(BaseModel):
    """Request to update the user's subscription tier."""

    tier: UserTier


class UserConsentUpdate(BaseModel):
    """Request to update user consent flags."""

    consent_telemetry: Optional[bool] = None
    consent_raw_text: Optional[bool] = None


class SessionEventOut(BaseModel):
    """Response model for events."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType
    payload: Optional[dict] = None
    created_at: datetime


class GroundingRequest(BaseModel):
    """Request model for explicit grounding."""

    mode: str = "auto"
    user_question: Optional[str] = None
    region_hint: Optional[str] = None
    max_queries: Optional[int] = None


class GroundingResponse(BaseModel):
    """Response model for explicit grounding."""

    grounding_pack: dict
    sources: List[dict] = []
    budget_spent: int = 0


class RouteGenerateRequest(BaseModel):
    """Request model for generating a single route branch."""

    variant: str = Field("LIKELY", description="Route variant: LIKELY, RISK, BEST, ALT.")
    existing_routes: List[dict] = Field(default_factory=list, description="Existing routes to avoid duplicating.")
    parent_message_id: Optional[int] = Field(
        None, description="Optional user message ID to anchor the branch."
    )


class RouteBranchOut(BaseModel):
    """Response model for a generated route branch."""

    branch_id: str
    thread_id: int
    parent_message_id: int
    variant: str
    counterparty_response: str
    rationale: str
    action_label: Optional[str] = None
    branch_label: Optional[str] = None
    created_at: str
    is_active: Optional[bool] = None


class BranchUpdateRequest(BaseModel):
    """Update a branch label or response."""

    branch_label: Optional[str] = None
    counterparty_response: Optional[str] = None


class BranchCopyRequest(BaseModel):
    """Copy a branch, optionally overriding label/response."""

    branch_label: Optional[str] = None
    counterparty_response: Optional[str] = None
