"""
LLM orchestration and chat loop logic.

This module wires a LangGraph state machine to build prompt context,
invoke LiteLLM for roleplay, and optionally generate coaching output.
Instructor is used for structured fact extraction when configured.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import (
    acompletion_with_retry,
    extract_completion_text,
    extract_json_object,
)

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None


logger = logging.getLogger(__name__)


class ExtractedFact(BaseModel):
    """Schema for a single extracted fact."""

    subject_entity_id: int = Field(..., description="ID of the subject entity for the fact.")
    key: str = Field(..., description="Short fact key, e.g. salary_offer.")
    value: str = Field(..., description="Canonical value as a string.")
    confidence: float = Field(0.6, description="Confidence score from 0-1.")


class FactExtractionResult(BaseModel):
    """Structured extraction output for candidate facts."""

    facts: List[ExtractedFact] = Field(default_factory=list)


class OrchestrationState(TypedDict, total=False):
    user_message: str
    visible_facts: List[Dict[str, Any]]
    grounding_pack: Optional[Dict[str, Any]]
    style: Optional[str]
    history: List[Dict[str, str]]
    topic_text: Optional[str]
    template_id: Optional[str]
    include_coach: bool
    stream_roleplay: bool
    prompt_messages: List[Dict[str, str]]
    roleplay_response: Optional[str]
    coach_panel: Optional[Dict[str, Any]]


class CoachSuggestion(BaseModel):
    reply: str = Field(..., description="Suggestion label (A/B/C).")
    text: str = Field(..., description="Suggested reply text.")
    intent: str = Field(..., description="Intent label for the suggestion.")


class CoachPanel(BaseModel):
    suggestions: List[CoachSuggestion] = Field(default_factory=list)
    strategy: Dict[str, str] = Field(default_factory=dict)
    critique: str = Field("")
    scenario_branches: List[Dict[str, str]] = Field(default_factory=list)
    after_action_report: str = Field("")


COACH_SYSTEM_PROMPT = """You are the Premium Coaching agent.
Provide coaching in a separate channel. Follow these rules:
- Avoid manipulation, coercion, or deception.
- Use only the provided context; unknown stays unknown.
- Output JSON only that matches the schema:
{"suggestions":[{"reply":"A","text":"...","intent":"..."}],
 "strategy":{"anchoring":"...","concessions":"...","questions":"...","red_lines":"..."},
 "critique":"...",
 "scenario_branches":[{"label":"...","next_step":"..."}],
 "after_action_report":"..."}
"""


_LANGFUSE_CLIENT: Optional[Any] = None
_ORCHESTRATION_GRAPH = None


def _get_langfuse_client() -> Optional[Any]:
    global _LANGFUSE_CLIENT
    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse import failed: %s", exc)
        return None
    _LANGFUSE_CLIENT = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return _LANGFUSE_CLIENT


def _log_langfuse_generation(
    name: str,
    model: str,
    messages: List[Dict[str, str]],
    output: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    client = _get_langfuse_client()
    if not client:
        return
    try:
        trace = client.trace(
            name=name,
            input=messages,
            metadata=metadata or {},
        )
        trace.generation(
            name=name,
            model=model,
            input=messages,
            output=output,
            metadata=metadata or {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse logging failed: %s", exc)


async def extract_candidate_facts(message: str, subject_entity_ids: List[int]) -> List[Dict[str, Any]]:
    """Extract candidate facts from a user message.

    A real implementation would call a structured extraction model
    (e.g., via the `instructor` library) to identify facts, their
    subjects and values.

    :param message: The raw user message.
    :param subject_entity_ids: IDs of entities attached to the session.
    :return: A list of dictionaries representing fact candidates.
    """
    if not subject_entity_ids:
        return []
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot extract facts.")
    system_prompt = (
        "Extract atomic facts from the user message. "
        "Only use subject_entity_id values from the provided list. "
        "Return an empty list when no facts are present. "
        'Output JSON only: {"facts":[{"subject_entity_id":1,"key":"...","value":"...","confidence":0.6}]}'
    )
    user_payload = {
        "message": message,
        "subject_entity_ids": subject_entity_ids,
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        "temperature": 0.0,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=FactExtractionResult, **completion_kwargs)
        return [fact.model_dump() for fact in response.facts]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Instructor extraction failed. Error: %s", exc)
    response = await acompletion_with_retry(**completion_kwargs)
    content = extract_completion_text(response)
    if not content:
        return []
    try:
        parsed = FactExtractionResult.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse fact extraction output. Error: %s", exc)
        extracted = extract_json_object(content)
        if extracted is None:
            return []
        parsed = FactExtractionResult.model_validate(extracted)
    return [fact.model_dump() for fact in parsed.facts]


async def _generate_roleplay_from_prompt(
    messages: List[Dict[str, str]],
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
) -> str:
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot generate roleplay.")
    try:
        completion_kwargs = {
            "model": settings.litellm_model,
            "messages": messages,
            "temperature": 0.7,
        }
        if settings.litellm_api_key:
            completion_kwargs["api_key"] = settings.litellm_api_key
        if settings.litellm_base_url:
            completion_kwargs["base_url"] = settings.litellm_base_url
        response = await acompletion_with_retry(**completion_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM roleplay response failed. Error: %s", exc)
        raise
    content = extract_completion_text(response)
    if not content:
        raise RuntimeError("LiteLLM returned an empty roleplay response.")
    _log_langfuse_generation(
        name="roleplay_response",
        model=settings.litellm_model,
        messages=messages,
        output=content.strip(),
        metadata={"style": style},
    )
    return content.strip()


async def generate_roleplay_response(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Generate a simulated counterparty response.

    The response is kept simple: it acknowledges the user's message
    and optionally mentions one visible fact. In a real system this
    would call a chat LLM with a carefully constructed prompt, ensure
    that unknown facts remain unknown and filter any coaching language.
    
    :param user_message: The content sent by the user.
    :param visible_facts: Facts visible to the counterparty.
    :param grounding_pack: Optional web grounding information.
    :param style: Counterparty persona style (polite, neutral, tough, busy, defensive).
    :return: A roleplay response string.
    """
    messages = build_roleplay_messages(user_message, visible_facts, grounding_pack, style, history)
    return await _generate_roleplay_from_prompt(
        messages, user_message, visible_facts, grounding_pack, style
    )


async def generate_roleplay_stream(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
    history: Optional[List[Dict[str, str]]] = None,
    prompt_messages: Optional[List[Dict[str, str]]] = None,
):
    """Stream a simulated counterparty response."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot stream roleplay.")
    messages = prompt_messages or build_roleplay_messages(
        user_message, visible_facts, grounding_pack, style, history
    )
    try:
        completion_kwargs = {
            "model": settings.litellm_model,
            "messages": messages,
            "temperature": 0.7,
            "stream": True,
        }
        if settings.litellm_api_key:
            completion_kwargs["api_key"] = settings.litellm_api_key
        if settings.litellm_base_url:
            completion_kwargs["base_url"] = settings.litellm_base_url
        stream = await acompletion_with_retry(**completion_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM roleplay streaming failed. Error: %s", exc)
        raise
    collected: List[str] = []
    async for chunk in stream:
        delta = _extract_stream_delta(chunk)
        if delta:
            collected.append(delta)
            yield delta
    if not collected:
        raise RuntimeError("LiteLLM streaming returned no content.")
    _log_langfuse_generation(
        name="roleplay_stream",
        model=settings.litellm_model,
        messages=messages,
        output="".join(collected).strip(),
        metadata={"style": style},
    )


def build_roleplay_messages(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
    history: Optional[List[Dict[str, str]]] = None,
    topic_text: Optional[str] = None,
    template_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    system_lines = [
        "You are the counterparty in a negotiation roleplay.",
        "Stay in character and respond naturally.",
        "Do not mention you are an AI or a model.",
        "Keep responses concise (2-4 sentences).",
        "Use only the provided context; ask a brief clarifying question if unsure.",
    ]
    if topic_text:
        system_lines.append(f"Session topic: {topic_text}")
    if template_id:
        system_lines.append(f"Template: {template_id}")
    if style:
        system_lines.append(f"Counterparty style: {style}.")
    if visible_facts:
        fact_lines = [f"- {fact.get('key')}: {fact.get('value')}" for fact in visible_facts]
        system_lines.append("Visible facts:\n" + "\n".join(fact_lines))
    if grounding_pack and grounding_pack.get("key_points"):
        grounding_lines = [f"- {item.get('text')}" for item in grounding_pack.get("key_points", [])]
        if grounding_lines:
            system_lines.append("Grounding notes:\n" + "\n".join(grounding_lines))
    messages: List[Dict[str, str]] = [{"role": "system", "content": "\n".join(system_lines)}]
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _route_coach(state: OrchestrationState) -> str:
    return "coach" if state.get("include_coach") else "end"


def _build_prompt_node(state: OrchestrationState) -> Dict[str, Any]:
    messages = build_roleplay_messages(
        state["user_message"],
        state.get("visible_facts", []),
        state.get("grounding_pack"),
        state.get("style"),
        state.get("history"),
        state.get("topic_text"),
        state.get("template_id"),
    )
    return {"prompt_messages": messages}


async def _roleplay_node(state: OrchestrationState) -> Dict[str, Any]:
    if state.get("stream_roleplay"):
        return {"roleplay_response": None}
    messages = state.get("prompt_messages")
    if not messages:
        messages = build_roleplay_messages(
            state["user_message"],
            state.get("visible_facts", []),
            state.get("grounding_pack"),
            state.get("style"),
            state.get("history"),
            state.get("topic_text"),
            state.get("template_id"),
        )
    response = await _generate_roleplay_from_prompt(
        messages,
        state["user_message"],
        state.get("visible_facts", []),
        state.get("grounding_pack"),
        state.get("style"),
    )
    return {"roleplay_response": response}


async def _coach_node(state: OrchestrationState) -> Dict[str, Any]:
    if not state.get("include_coach"):
        return {}
    coach_panel = await generate_coach_response(
        state["user_message"],
        state.get("visible_facts", []),
        state.get("grounding_pack"),
    )
    return {"coach_panel": coach_panel}


def _get_orchestration_graph():
    global _ORCHESTRATION_GRAPH
    if _ORCHESTRATION_GRAPH is not None:
        return _ORCHESTRATION_GRAPH
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph is required for orchestration but is not available.")
    graph = StateGraph(OrchestrationState)
    graph.add_node("build_prompt", _build_prompt_node)
    graph.add_node("roleplay", _roleplay_node)
    graph.add_node("coach", _coach_node)
    graph.set_entry_point("build_prompt")
    graph.add_edge("build_prompt", "roleplay")
    graph.add_conditional_edges(
        "roleplay",
        _route_coach,
        {
            "coach": "coach",
            "end": END,
        },
    )
    graph.add_edge("coach", END)
    _ORCHESTRATION_GRAPH = graph.compile()
    return _ORCHESTRATION_GRAPH


async def run_orchestration(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
    history: Optional[List[Dict[str, str]]],
    topic_text: Optional[str] = None,
    template_id: Optional[str] = None,
    include_coach: bool = False,
    stream_roleplay: bool = True,
) -> OrchestrationState:
    state: OrchestrationState = {
        "user_message": user_message,
        "visible_facts": visible_facts,
        "grounding_pack": grounding_pack,
        "style": style,
        "history": history or [],
        "topic_text": topic_text,
        "template_id": template_id,
        "include_coach": include_coach,
        "stream_roleplay": stream_roleplay,
    }
    graph = _get_orchestration_graph()
    return await graph.ainvoke(state)


def _extract_stream_delta(chunk: Any) -> Optional[str]:
    try:
        return chunk["choices"][0]["delta"].get("content")
    except Exception:
        pass
    try:
        return chunk.choices[0].delta.content
    except Exception:
        pass
    try:
        return chunk["choices"][0].get("text")
    except Exception:
        pass
    try:
        return chunk.choices[0].text
    except Exception:
        return None


async def generate_coach_response(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate coaching suggestions for premium users.

    :return: A dictionary with keys describing the coaching content.
    """
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot generate coach output.")
    payload = {
        "user_message": user_message,
        "visible_facts": visible_facts,
        "grounding_pack": grounding_pack or {},
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.3,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=CoachPanel, **completion_kwargs)
        return response.model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Coach generation failed. Error: %s", exc)
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty coach response.")
        return CoachPanel.model_validate_json(content).model_dump()
