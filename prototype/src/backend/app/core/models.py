from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator


class BaseModelWithExtra(BaseModel):
    class Config:
        extra = "allow"


class CaseStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    SIMULATED = "SIMULATED"


class Domain(str, Enum):
    GENERAL = "GENERAL"
    JOB_OFFER_COMP = "JOB_OFFER_COMP"
    RENT_HOUSING = "RENT_HOUSING"
    PROCUREMENT_VENDOR = "PROCUREMENT_VENDOR"
    SERVICES_CONTRACTOR = "SERVICES_CONTRACTOR"


class Channel(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    IN_PERSON = "IN_PERSON"
    EMAIL = "EMAIL"
    DM = "DM"


class ParameterValueType(str, Enum):
    MONEY = "MONEY"
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    DATE = "DATE"
    ENUM = "ENUM"
    BOOLEAN = "BOOLEAN"


class ParameterClass(str, Enum):
    NON_NEGOTIABLE = "NON_NEGOTIABLE"
    HARD_IN_RUN_REVISABLE = "HARD_IN_RUN_REVISABLE"
    PREFERENCE = "PREFERENCE"


class ParameterDisclosure(str, Enum):
    PRIVATE = "PRIVATE"
    SHAREABLE = "SHAREABLE"
    CONDITIONAL = "CONDITIONAL"


class AppliesToScope(str, Enum):
    OFFER = "OFFER"
    DISCLOSURE = "DISCLOSURE"
    SCHEDULE = "SCHEDULE"
    OTHER = "OTHER"


class ObjectiveType(str, Enum):
    OFFER_VECTOR = "OFFER_VECTOR"
    SINGLE_VALUE = "SINGLE_VALUE"


class IssueType(str, Enum):
    PRICE = "PRICE"
    SALARY = "SALARY"
    DATE = "DATE"
    SCOPE = "SCOPE"
    RISK = "RISK"
    BENEFIT = "BENEFIT"
    OTHER = "OTHER"


class IssueDirection(str, Enum):
    MINIMIZE = "MINIMIZE"
    MAXIMIZE = "MAXIMIZE"


class IssueUnit(str, Enum):
    GBP = "GBP"
    USD = "USD"
    days = "days"
    text = "text"


class ActionType(str, Enum):
    PROPOSE_OFFER = "PROPOSE_OFFER"
    COUNTER_OFFER = "COUNTER_OFFER"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    CONCEDE = "CONCEDE"
    TRADE = "TRADE"
    PROPOSE_PACKAGE = "PROPOSE_PACKAGE"
    ASK_INFO = "ASK_INFO"
    REQUEST_CRITERIA = "REQUEST_CRITERIA"
    SUMMARIZE_VALIDATE = "SUMMARIZE_VALIDATE"
    DEFER_AND_SCHEDULE = "DEFER_AND_SCHEDULE"
    ESCALATE_TO_DECIDER = "ESCALATE_TO_DECIDER"
    WALK_AWAY = "WALK_AWAY"
    TIMEOUT_END = "TIMEOUT_END"


class Phase(str, Enum):
    DISCOVERY = "DISCOVERY"
    POSITIONING = "POSITIONING"
    TRADING = "TRADING"
    CLOSING = "CLOSING"


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEUTRAL = "NEUTRAL"


class RunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"



class StrategyUI(BaseModelWithExtra):
    card_title: str
    card_summary: str
    icon: str


class StrategyApplicability(BaseModelWithExtra):
    domains: List[Domain]


class StrategyRequires(BaseModelWithExtra):
    case_fields: List[str]


class Strategy(BaseModelWithExtra):
    strategy_id: str
    revision: int
    name: str
    category: str
    tags: Optional[List[str]] = None
    summary: str
    goal: Optional[str] = None
    counterparty_guidance: List[str]
    applicability: StrategyApplicability
    requires: StrategyRequires
    preferred_actions: List[ActionType]
    ui: StrategyUI
    online_reference: str


class ParameterAppliesTo(BaseModelWithExtra):
    scope: AppliesToScope
    issue_id: Optional[str] = None
    path: Optional[str] = None


class Parameter(BaseModelWithExtra):
    param_id: str
    label: str
    value_type: ParameterValueType
    value: Any
    class_: ParameterClass = Field(alias="class")
    disclosure: ParameterDisclosure = ParameterDisclosure.SHAREABLE
    allow_rethink_suggestions: Optional[bool] = None
    applies_to: ParameterAppliesTo

    @root_validator(pre=True)
    def _default_disclosure(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Default disclosure based on enforcement class when not provided."""
        if values.get("disclosure") not in (None, ""):
            return values
        class_value = values.get("class", values.get("class_"))
        if isinstance(class_value, ParameterClass):
            class_value = class_value.value
        if class_value == ParameterClass.PREFERENCE.value:
            values["disclosure"] = ParameterDisclosure.SHAREABLE.value
        else:
            values["disclosure"] = ParameterDisclosure.PRIVATE.value
        return values


class ObjectiveValue(BaseModelWithExtra):
    type: ObjectiveType
    value: Any


class Objectives(BaseModelWithExtra):
    target: ObjectiveValue
    reservation: ObjectiveValue
    no_deal_acceptable: bool = False
    issue_weights: Dict[str, float]


class IssueBounds(BaseModelWithExtra):
    min: Optional[Any] = None
    max: Optional[Any] = None


class Issue(BaseModelWithExtra):
    issue_id: str
    name: str
    type: IssueType
    direction: IssueDirection
    unit: IssueUnit
    bounds: Optional[IssueBounds] = None


class CounterpartyCalibration(BaseModelWithExtra):
    answers: Dict[str, Any] = Field(default_factory=dict)


class PersonaWeight(BaseModelWithExtra):
    persona_id: str
    weight: float


class CounterpartyAssumptions(BaseModelWithExtra):
    calibration: CounterpartyCalibration
    persona_distribution: List[PersonaWeight]
    notes: Optional[str] = None


class Clarification(BaseModelWithExtra):
    question: str
    answer: Optional[Any] = None


class Controls(BaseModelWithExtra):
    outcome_vs_agreement: float
    speed_vs_thoroughness: float
    risk_tolerance: float
    relationship_sensitivity: float
    info_sharing: float
    creativity_vs_discipline: float
    constraint_confidence: float


class Mode(BaseModelWithExtra):
    auto_enabled: bool
    advanced_enabled: bool
    enabled_strategies: List[str]
    pinned_strategy: Optional[str] = None


class CaseSnapshot(BaseModelWithExtra):
    case_id: str
    revision: int
    created_at: str
    status: CaseStatus
    topic: str
    domain: Domain
    channel: Channel
    parameters: List[Parameter]
    objectives: Objectives
    issues: Optional[List[Issue]] = None
    user_issues: Optional[List[Issue]] = None
    counterparty_issues: Optional[List[Issue]] = None
    counterparty_assumptions: CounterpartyAssumptions
    clarifications: Optional[List[Clarification]] = None
    controls: Controls
    mode: Mode
    controls_ui: Optional[Dict[str, Any]] = None


class PersonaBehavior(BaseModelWithExtra):
    acceptance_threshold: float
    stall_probability: float
    escalation_probability: float


class PersonaDims(BaseModelWithExtra):
    flexibility: float
    policy_rigidity: float
    cooperativeness: float
    authority_level: float
    time_pressure: float
    batna_strength: float


class Persona(BaseModelWithExtra):
    persona_id: str
    label: str
    dims: PersonaDims
    behavior: PersonaBehavior


class PersonaPack(BaseModelWithExtra):
    personas: List[Persona]


class Offer(BaseModelWithExtra):
    offer_id: str
    by_issue: Dict[str, Any]
    proposed_by: str


class StrategyScore(BaseModelWithExtra):
    id: str
    score: float


class ActionProbability(BaseModelWithExtra):
    action: ActionType
    p: float


class ActionTaken(BaseModelWithExtra):
    type: ActionType
    payload: Dict[str, Any]


class ConstraintCheck(BaseModelWithExtra):
    param_id: str
    result: str


class StateDelta(BaseModelWithExtra):
    offers_added: int
    concession: Optional[Dict[str, Any]] = None


class Turn(BaseModelWithExtra):
    turn_index: int
    speaker: str
    message_text: str
    conversation: List[Dict[str, Any]]
    outcome: Outcome
    strategy_suggestions: Optional[List[Dict[str, Any]]] = None
    used_strategies: Optional[List[str]] = None
    action: Optional[Dict[str, Any]] = None


class SimulationRun(BaseModelWithExtra):
    run_id: str
    case_id: str
    seed: int
    persona_id: str
    turns: List[Turn]
    outcome: Outcome
    user_utility: float
    summary: Optional[Dict[str, Any]] = None
    status: RunStatus = RunStatus.COMPLETED
    session_id: Optional[str] = None
    pending_question_id: Optional[str] = None
    max_turns: Optional[int] = None
    max_questions: Optional[int] = None


class PromptVersion(BaseModelWithExtra):
    prompt_id: str
    prompt_version: str


class RunTrace(BaseModelWithExtra):
    seed: int
    persona_id: str
    controls: Controls
    enabled_strategies: List[str]
    prompt_versions: List[PromptVersion]


class AgentCallTrace(BaseModelWithExtra):
    agent_name: str
    prompt_id: str
    prompt_version: str
    prompt_variables: Dict[str, Any]
    prompt_text: str
    raw_output: str
    parsed_output: Dict[str, Any]
    model_params: Optional[Dict[str, Any]] = None
    validation_result: Dict[str, Any]
    tool_calls: List[Any]
    token_usage: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None


class TraceBundle(BaseModelWithExtra):
    run_trace: RunTrace
    turn_traces: List[Turn]
    agent_call_traces: List[AgentCallTrace]


class SimulationRequest(BaseModelWithExtra):
    runs: int
    max_turns: int
    mode: str
    max_questions: Optional[int] = None
    session_id: Optional[str] = None


class CalibrationRequest(BaseModelWithExtra):
    calibration: CounterpartyCalibration


class OutcomeRates(BaseModelWithExtra):
    PASS: float
    FAIL: float
    NEUTRAL: float


class Insights(BaseModelWithExtra):
    outcome_rates: Dict[str, Any]
    utility_distribution: List[float]
    turns_to_termination: List[int]
    most_binding_constraints: List[Dict[str, Any]]
    top_strategy_sequences: List[Dict[str, Any]]
    strategy_usage_summary: List[Dict[str, Any]]
    win_patterns: List[Dict[str, Any]]
    loss_patterns: List[Dict[str, Any]]
    compromise_levers: List[Dict[str, Any]]
