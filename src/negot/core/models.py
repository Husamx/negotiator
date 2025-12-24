"""
Database models for the Negotiation Companion.

This module defines the ORM classes corresponding to the tables
described in `docs/DATA_MODEL.md`. The models are designed with
SQLAlchemy's asynchronous support in mind. Relationships are
established where appropriate to enable convenient navigation between
objects while still keeping queries explicit and efficient.

If you modify these models, remember to generate and apply an Alembic
migration for persistent databases. For tests and development the
``init_db_schema`` helper can create tables on the fly.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UserTier(enum.Enum):
    """Subscription tiers for users."""

    standard = "standard"
    premium = "premium"


class MessageRole(enum.Enum):
    """Possible roles for a chat message."""

    user = "user"
    counterparty = "counterparty"
    system = "system"
    coach = "coach"


class KnowledgeStatus(enum.Enum):
    """Status of a knowledge edge representing epistemic state."""

    confirmed = "confirmed"
    assumed = "assumed"
    false_belief = "false_belief"


class KnowledgeSource(enum.Enum):
    """Source of knowledge edges."""

    user_told = "user_told"
    observed = "observed"
    inferred = "inferred"
    public = "public"
    third_party = "third_party"


class KnowledgeScope(enum.Enum):
    """Scope for facts and knowledge edges."""

    global_scope = "global"
    session_scope = "session"


class EventType(enum.Enum):
    """Enumerates the event types defined in docs/EVENTS.md."""

    session_created = "SESSION_CREATED"
    session_template_selected = "SESSION_TEMPLATE_SELECTED"
    session_setup_question_answered = "SESSION_SETUP_QUESTION_ANSWERED"
    session_started = "SESSION_STARTED"
    session_ended = "SESSION_ENDED"
    message_user_sent = "MESSAGE_USER_SENT"
    message_counterparty_sent = "MESSAGE_COUNTERPARTY_SENT"
    message_coach_sent = "MESSAGE_COACH_SENT"
    entity_created = "ENTITY_CREATED"
    entity_edited = "ENTITY_EDITED"
    entity_deleted = "ENTITY_DELETED"
    entity_attached = "ENTITY_ATTACHED_TO_SESSION"
    entity_detached = "ENTITY_DETACHED_FROM_SESSION"
    fact_extracted = "FACT_EXTRACTED"
    fact_suggested = "FACT_SUGGESTED_FOR_MEMORY"
    fact_confirmed = "FACT_CONFIRMED_FOR_MEMORY"
    fact_rejected = "FACT_REJECTED_FOR_MEMORY"
    relationship_created = "RELATIONSHIP_CREATED"
    relationship_deleted = "RELATIONSHIP_DELETED"
    knowledge_edge_seeded = "KNOWLEDGE_EDGE_SEEDED_FROM_PRIOR"
    knowledge_edge_updated = "KNOWLEDGE_EDGE_UPDATED"
    disclosure_in_chat = "DISCLOSURE_IN_CHAT"
    web_grounding_decided = "WEB_GROUNDING_DECIDED"
    web_grounding_query_planned = "WEB_GROUNDING_QUERY_PLANNED"
    web_grounding_called = "WEB_GROUNDING_CALLED"
    web_grounding_pack_created = "WEB_GROUNDING_PACK_CREATED"
    web_grounding_shown = "WEB_GROUNDING_SHOWN_TO_USER"
    template_other_triggered = "TEMPLATE_OTHER_TRIGGERED"
    template_draft_generated = "TEMPLATE_DRAFT_GENERATED"
    template_patch_proposed = "TEMPLATE_PATCH_PROPOSED"
    template_proposal_submitted = "TEMPLATE_PROPOSAL_SUBMITTED_FOR_REVIEW"
    template_proposal_approved = "TEMPLATE_PROPOSAL_APPROVED"
    template_proposal_rejected = "TEMPLATE_PROPOSAL_REJECTED"
    coach_panel_shown = "COACH_PANEL_SHOWN"
    coach_suggestion_shown = "COACH_SUGGESTION_SHOWN"
    coach_suggestion_used = "COACH_SUGGESTION_USED"
    coach_suggestion_rated = "COACH_SUGGESTION_RATED"
    message_stream_started = "MESSAGE_STREAM_STARTED"
    message_stream_ended = "MESSAGE_STREAM_ENDED"
    orchestration_context_built = "ORCHESTRATION_CONTEXT_BUILT"
    strategy_pack_loaded = "STRATEGY_PACK_LOADED"
    strategy_selection_run = "STRATEGY_SELECTION_RUN"
    strategy_selected = "STRATEGY_SELECTED"
    strategy_execution_run = "STRATEGY_EXECUTION_RUN"
    strategy_execution_completed = "STRATEGY_EXECUTION_COMPLETED"


class TemplateProposalStatus(enum.Enum):
    """Workflow state for template proposals."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    """Represents an end user of the application."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tier: Mapped[UserTier] = mapped_column(Enum(UserTier), default=UserTier.standard)
    consent_telemetry: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_raw_text: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user")
    entities: Mapped[list["Entity"]] = relationship("Entity", back_populates="owner")


class Session(Base):
    """A negotiation session between a user and a simulated counterparty."""

    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    template_id: Mapped[str] = mapped_column(String(length=50), default="other")
    title: Mapped[str] = mapped_column(String(length=200), default="Negotiation Session")
    topic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counterparty_style: Mapped[Optional[str]] = mapped_column(String(length=20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationship
    user: Mapped[User] = relationship("User", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    attached_entities: Mapped[list["Entity"]] = relationship(
        "Entity",
        secondary="session_entities",
        back_populates="sessions",
    )
    facts: Mapped[list["Fact"]] = relationship("Fact", back_populates="session")
    case_snapshot: Mapped[Optional["CaseSnapshot"]] = relationship(
        "CaseSnapshot", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    strategy_selections: Mapped[list["StrategySelection"]] = relationship(
        "StrategySelection", back_populates="session", cascade="all, delete-orphan"
    )
    strategy_executions: Mapped[list["StrategyExecution"]] = relationship(
        "StrategyExecution", back_populates="session", cascade="all, delete-orphan"
    )


class SessionEntity(Base):
    """Join table associating entities with sessions."""

    __tablename__ = "session_entities"
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    """A single chat message within a session."""

    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(length=20), nullable=True)
    token_usage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    safety_flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="messages")


class CaseSnapshot(Base):
    """Structured snapshot of a negotiation case for strategy selection/execution."""

    __tablename__ = "case_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="case_snapshot")


class StrategySelection(Base):
    """Stores LLM strategy selection outputs for a session."""

    __tablename__ = "strategy_selections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    strategy_pack_id: Mapped[str] = mapped_column(String(length=50), nullable=False)
    strategy_pack_version: Mapped[Optional[str]] = mapped_column(String(length=20), nullable=True)
    selected_strategy_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    selection_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="strategy_selections")


class StrategyExecution(Base):
    """Stores strategy execution outputs and artifacts for a session."""

    __tablename__ = "strategy_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    strategy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    case_patches: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    judge_outputs: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    trace: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[Session] = relationship("Session", back_populates="strategy_executions")


class Entity(Base):
    """Represents a knowledge graph node (person, organization, etc.)."""

    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(length=50), nullable=False)
    name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner: Mapped[User] = relationship("User", back_populates="entities")
    sessions: Mapped[list[Session]] = relationship(
        "Session",
        secondary="session_entities",
        back_populates="attached_entities",
    )
    facts: Mapped[list["Fact"]] = relationship("Fact", back_populates="subject")


class Relationship(Base):
    """Represents a typed edge between two entities."""

    __tablename__ = "relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    src_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    rel_type: Mapped[str] = mapped_column(String(length=50), nullable=False)
    dst_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "src_entity_id", "rel_type", "dst_entity_id", name="uix_relationship"),)


class Fact(Base):
    """Atomic statement about an entity."""

    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    subject_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(length=100), nullable=False)
    value: Mapped[str] = mapped_column(String(length=200), nullable=False)
    value_type: Mapped[str] = mapped_column(String(length=50), default="str")
    unit: Mapped[Optional[str]] = mapped_column(String(length=20), nullable=True)
    scope: Mapped[KnowledgeScope] = mapped_column(Enum(KnowledgeScope), default=KnowledgeScope.global_scope)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(length=100), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(length=20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subject: Mapped[Entity] = relationship("Entity", back_populates="facts")
    knowledge_edges: Mapped[list["KnowledgeEdge"]] = relationship("KnowledgeEdge", back_populates="fact")
    session: Mapped[Optional[Session]] = relationship("Session", back_populates="facts")


class KnowledgeEdge(Base):
    """Represents who knows a fact and under what status."""

    __tablename__ = "knowledge_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    knower_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id"), nullable=False)
    status: Mapped[KnowledgeStatus] = mapped_column(Enum(KnowledgeStatus), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[KnowledgeSource] = mapped_column(Enum(KnowledgeSource), nullable=False)
    scope: Mapped[KnowledgeScope] = mapped_column(Enum(KnowledgeScope), default=KnowledgeScope.global_scope)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    fact: Mapped[Fact] = relationship("Fact", back_populates="knowledge_edges")


class Event(Base):
    """Append-only log of application events."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TemplateDraft(Base):
    """User-local template draft generated for an unknown topic."""

    __tablename__ = "template_drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(length=120), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TemplateProposal(Base):
    """Template proposal submitted for admin review."""

    __tablename__ = "template_proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    draft_id: Mapped[Optional[int]] = mapped_column(ForeignKey("template_drafts.id"), nullable=True)
    status: Mapped[TemplateProposalStatus] = mapped_column(
        Enum(TemplateProposalStatus), default=TemplateProposalStatus.pending
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
