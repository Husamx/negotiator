"""
LLM-powered intake question planner.

This agent chooses the minimal set of questions needed to start a session.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object

logger = logging.getLogger(__name__)

MAX_INTAKE_QUESTIONS = 5
DEFAULT_INTAKE_GOAL = (
    "Collect only the critical unknowns needed to start realistic roleplay, "
    "maximize realism, and minimize the number of questions."
)

INTAKE_QUESTION_SYSTEM_PROMPT = """You are the Intake Question Agent.
Treat this as a reinforcement learning decision:
- State: the current conversation context and known facts.
- Action: the minimal set of questions to ask next.
- Reward: higher realism and lower user burden; penalize unnecessary questions.

Constraints:
- Ask 0 to 5 questions, as few as possible.
- Ask only what is necessary to start roleplay; do not coach or advise.
- Use only the provided state; unknown stays unknown.
- Output JSON only: {"questions": ["..."]}.
"""


class IntakeQuestionPlan(BaseModel):
    """Structured response for intake questions."""

    questions: List[str] = Field(default_factory=list, description="Ordered list of questions.")

    @field_validator("questions")
    @classmethod
    def validate_questions(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen = set()
        for item in value:
            if not item:
                continue
            text = str(item).strip()
            if not text:
                continue
            if text in seen:
                continue
            cleaned.append(text)
            seen.add(text)
        if len(cleaned) > MAX_INTAKE_QUESTIONS:
            cleaned = cleaned[:MAX_INTAKE_QUESTIONS]
        return cleaned


def _build_state_payload(
    topic_text: str,
    template_id: str,
    counterparty_style: Optional[str],
    attached_entities: Sequence[Dict[str, Any]],
    history: Optional[List[Dict[str, str]]],
) -> Dict[str, Any]:
    return {
        "topic_text": topic_text,
        "template_id": template_id,
        "counterparty_style": counterparty_style,
        "attached_entities": list(attached_entities),
        "history": history or [],
    }


async def generate_intake_questions(
    *,
    topic_text: str,
    template_id: str,
    counterparty_style: Optional[str] = None,
    attached_entities: Optional[Sequence[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    goal: Optional[str] = None,
) -> List[str]:
    """Plan minimal intake questions using an LLM agent."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot plan intake questions.")
    state = _build_state_payload(
        topic_text,
        template_id,
        counterparty_style,
        attached_entities or [],
        history,
    )
    payload = {"state": state, "goal": goal or DEFAULT_INTAKE_GOAL}
    messages = [
        {"role": "system", "content": INTAKE_QUESTION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": messages,
        "temperature": 0.2,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(
            response_model=IntakeQuestionPlan,
            **completion_kwargs,
        )
        return response.questions
    except Exception as exc:  # noqa: BLE001
        logger.warning("Instructor intake planning failed; falling back. Error: %s", exc)
    response = await acompletion_with_retry(**completion_kwargs)
    content = extract_completion_text(response)
    if not content:
        raise RuntimeError("LiteLLM returned an empty intake plan.")
    try:
        plan = IntakeQuestionPlan.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse intake questions. Error: %s", exc)
        extracted = extract_json_object(content)
        if extracted is None:
            raise
        plan = IntakeQuestionPlan.model_validate(extracted)
    return plan.questions
