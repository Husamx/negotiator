from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.core.models import ActionType


class AgentAction(BaseModel):
    type: ActionType
    payload: Dict[str, Any] = Field(default_factory=dict)


class AgentMeta(BaseModel):
    selected_strategy_id: Optional[str] = None
    followed_strategy: Optional[bool] = None
    policy_override_reason: Optional[str] = None
    confidence: Optional[float] = None
    persona_id: Optional[str] = None


class AgentActionOutput(BaseModel):
    action: AgentAction
    message_text: Optional[str] = None
    meta: Optional[AgentMeta] = None


class WorldValidationOutput(BaseModel):
    status: str
    reason: Optional[str] = None


class WorldOutcomeOutput(BaseModel):
    outcome: str
    reason: Optional[str] = None


class ExtractorOutput(BaseModel):
    signals: Dict[str, float] = Field(default_factory=dict)
    summary: Optional[str] = None
    confidence: Optional[float] = None


class UIConfigOutput(BaseModel):
    controls_ui: Dict[str, Any] = Field(default_factory=dict)


class CounterpartyHint(BaseModel):
    control_id: str
    label: str
    definition: str
    example: str


class CounterpartyHintExamplesOutput(BaseModel):
    examples: Dict[str, str] = Field(default_factory=dict)


class CaseQuestion(BaseModel):
    rank: int
    question: str


class CaseQuestionsOutput(BaseModel):
    questions: list[CaseQuestion] = Field(default_factory=list)


class RoleplayOutput(BaseModel):
    message_text: str
    action: AgentAction
    used_strategies: Optional[list[str]] = None


class ExtractedOffer(BaseModel):
    issue_id: Optional[str] = None
    value_text: str
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class ExtractedConcession(BaseModel):
    issue_id: Optional[str] = None
    from_value_text: Optional[str] = None
    to_value_text: Optional[str] = None
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class ExtractedPackageItem(BaseModel):
    issue_id: Optional[str] = None
    value_text: str


class ExtractedPackage(BaseModel):
    items: list[ExtractedPackageItem] = Field(default_factory=list)
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class ExtractedAsk(BaseModel):
    text: str
    target_issue_id: Optional[str] = None
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class ExtractedObjection(BaseModel):
    text: str
    target_issue_id: Optional[str] = None
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class ExtractedArgument(BaseModel):
    type: str
    text: str
    speaker: str
    evidence: Optional[str] = None
    turn_index: Optional[int] = None


class WorldExtractOutput(BaseModel):
    offers: list[ExtractedOffer] = Field(default_factory=list)
    concessions: list[ExtractedConcession] = Field(default_factory=list)
    packages: list[ExtractedPackage] = Field(default_factory=list)
    asks: list[ExtractedAsk] = Field(default_factory=list)
    objections: list[ExtractedObjection] = Field(default_factory=list)
    arguments: list[ExtractedArgument] = Field(default_factory=list)


class WorldRunSummaryOutput(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)


class BucketInsight(BaseModel):
    claim: str
    support_count: int = 0
    example_run_ids: list[str] = Field(default_factory=list)
    example_snippets: list[str] = Field(default_factory=list)


class BucketInsightsOutput(BaseModel):
    bucket: str
    insights: list[BucketInsight] = Field(default_factory=list)
