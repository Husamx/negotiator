"""
LLM orchestration and chat loop logic.

This module wires a LangGraph state machine to build prompt context,
invoke LiteLLM for roleplay, and optionally generate coaching output.
Instructor is used for structured fact extraction when configured.
Fallback responses keep the MVP functional without external LLMs.
"""
from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Dict, List, Optional, TypedDict

from litellm import acompletion
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None


logger = logging.getLogger(__name__)

LLM_RETRY_ATTEMPTS = 3


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
    include_coach: bool
    stream_roleplay: bool
    prompt_messages: List[Dict[str, str]]
    roleplay_response: Optional[str]
    coach_panel: Optional[Dict[str, Any]]


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


@retry(
    stop=stop_after_attempt(LLM_RETRY_ATTEMPTS),
    wait=wait_exponential(min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _acompletion_with_retry(**kwargs: Any) -> Any:
    return await acompletion(**kwargs)


async def extract_candidate_facts(message: str, subject_entity_ids: List[int]) -> List[Dict[str, Any]]:
    """Extract candidate facts from a user message.

    A real implementation would call a structured extraction model
    (e.g., via the `instructor` library) to identify facts, their
    subjects and values. The MVP provides a trivial extractor that
    returns an empty list. You could extend this with simple regex
    rules (e.g., detect numbers) if desired.

    :param message: The raw user message.
    :param subject_entity_ids: IDs of entities attached to the session.
    :return: A list of dictionaries representing fact candidates.
    """
    if not subject_entity_ids:
        return []
    settings = get_settings()
    if settings.env != "test" and settings.litellm_model:
        try:
            from instructor import from_litellm

            client = from_litellm(_acompletion_with_retry)
            system_prompt = (
                "Extract atomic facts from the user message. "
                "Only use subject_entity_id values from the provided list. "
                "Return an empty list when no facts are present."
            )
            user_payload = {
                "message": message,
                "subject_entity_ids": subject_entity_ids,
            }
            response = await client(
                model=settings.litellm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
                temperature=0.0,
                response_model=FactExtractionResult,
            )
            return [fact.model_dump() for fact in response.facts]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Instructor extraction failed; falling back. Error: %s", exc)
    match = re.search(r"\b(\d{2,3}(?:[,\d]{0,6})?)\b", message)
    if not match:
        return []
    raw_value = match.group(1).replace(",", "")
    key = "mentioned_amount"
    if "salary" in message.lower():
        key = "salary_offer"
    return [
        {
            "subject_entity_id": subject_entity_ids[0],
            "key": key,
            "value": raw_value,
        }
    ]


async def _generate_roleplay_from_prompt(
    messages: List[Dict[str, str]],
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
) -> str:
    settings = get_settings()
    if settings.env != "test" and settings.litellm_model:
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
            response = await _acompletion_with_retry(**completion_kwargs)
            content = _extract_completion_text(response)
            if content:
                _log_langfuse_generation(
                    name="roleplay_response",
                    model=settings.litellm_model,
                    messages=messages,
                    output=content.strip(),
                    metadata={"style": style},
                )
                return content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM roleplay response failed; falling back. Error: %s", exc)
    return _fallback_roleplay_response(user_message, visible_facts, grounding_pack, style)


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
):
    """Stream a simulated counterparty response."""
    settings = get_settings()
    if settings.env != "test" and settings.litellm_model:
        messages = build_roleplay_messages(user_message, visible_facts, grounding_pack, style, history)
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
            stream = await _acompletion_with_retry(**completion_kwargs)
            collected: List[str] = []
            async for chunk in stream:
                delta = _extract_stream_delta(chunk)
                if delta:
                    collected.append(delta)
                    yield delta
            if collected:
                _log_langfuse_generation(
                    name="roleplay_stream",
                    model=settings.litellm_model,
                    messages=messages,
                    output="".join(collected).strip(),
                    metadata={"style": style},
                )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM roleplay streaming failed; falling back. Error: %s", exc)
    fallback = _fallback_roleplay_response(user_message, visible_facts, grounding_pack, style)
    for piece in _iter_text_chunks(fallback):
        yield piece


def _extract_completion_text(response: Any) -> Optional[str]:
    """Extract the text content from a LiteLLM completion response."""
    try:
        return response["choices"][0]["message"]["content"]
    except Exception:
        pass
    try:
        return response.choices[0].message.content
    except Exception:
        return None


def build_roleplay_messages(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    system_lines = [
        "You are the counterparty in a negotiation roleplay.",
        "Stay in character and respond naturally.",
        "Do not mention you are an AI or a model.",
        "Keep responses concise (2-4 sentences).",
        "Use only the provided context; ask a brief clarifying question if unsure.",
    ]
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
        logger.warning("LangGraph is not available; using fallback orchestration.")
        return None
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
    include_coach: bool,
    stream_roleplay: bool,
) -> OrchestrationState:
    state: OrchestrationState = {
        "user_message": user_message,
        "visible_facts": visible_facts,
        "grounding_pack": grounding_pack,
        "style": style,
        "history": history or [],
        "include_coach": include_coach,
        "stream_roleplay": stream_roleplay,
    }
    graph = _get_orchestration_graph()
    if graph is None:
        prompt_messages = build_roleplay_messages(
            user_message,
            visible_facts,
            grounding_pack,
            style,
            history,
        )
        roleplay_response = None
        if not stream_roleplay:
            roleplay_response = await _generate_roleplay_from_prompt(
                prompt_messages,
                user_message,
                visible_facts,
                grounding_pack,
                style,
            )
        coach_panel = None
        if include_coach:
            coach_panel = await generate_coach_response(
                user_message, visible_facts, grounding_pack
            )
        state.update(
            {
                "prompt_messages": prompt_messages,
                "roleplay_response": roleplay_response,
                "coach_panel": coach_panel,
            }
        )
        return state
    return await graph.ainvoke(state)


def _fallback_roleplay_response(
    user_message: str,
    visible_facts: List[Dict[str, Any]],
    grounding_pack: Optional[Dict[str, Any]],
    style: Optional[str],
) -> str:
    style_prefix = ""
    if style:
        style_map = {
            "polite": "I'm trying to be polite: ",
            "neutral": "",
            "tough": "Listen, ",
            "busy": "I'm busy, but ",
            "defensive": "I feel defensive, so ",
        }
        style_prefix = style_map.get(style.lower(), "")
    fact_note = ""
    if visible_facts:
        # pick a random fact to mention
        fact = random.choice(visible_facts)
        fact_note = f" I remember that {fact.get('key')} is {fact.get('value')}."
    grounding_note = ""
    if grounding_pack and grounding_pack.get("key_points"):
        grounding_note = " I have some background information that might be relevant."
    return f"{style_prefix}you said: '{user_message}'.{fact_note}{grounding_note}"


def _iter_text_chunks(text: str, chunk_size: int = 8) -> List[str]:
    words = text.split(" ")
    if len(words) <= 1:
        return [text]
    chunks = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= chunk_size:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    spaced = [chunks[0]]
    for chunk in chunks[1:]:
        spaced.append(" " + chunk)
    return spaced


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

    The MVP returns a static set of suggestions with intent labels.
    A real implementation would call a different language model with
    a coaching prompt and enforce premium guardrails.
    
    :return: A dictionary with keys describing the coaching content.
    """
    suggestions = [
        {"reply": "A", "text": "Acknowledge their point and ask a clarifying question.", "intent": "clarify"},
        {"reply": "B", "text": "State your desired outcome clearly.", "intent": "assert"},
        {"reply": "C", "text": "Offer a compromise to reach mutual agreement.", "intent": "compromise"},
    ]
    strategy = {
        "anchoring": "Start with a high but reasonable demand to anchor the negotiation.",
        "concessions": "Plan what you are willing to give up and when.",
        "questions": "Prepare questions to understand their motivations.",
        "red_lines": "Know your non‑negotiable boundaries.",
    }
    after_action = "Consider how the conversation went and what you could improve next time."
    critique = "Your message is clear, but you could anchor your request more explicitly."
    scenario_branches = [
        {"label": "Counterparty agrees", "next_step": "Ask about timelines and next steps."},
        {"label": "Counterparty pushes back", "next_step": "Reframe with market data or role scope."},
        {"label": "Counterparty delays", "next_step": "Ask what information they need to proceed."},
    ]
    return {
        "suggestions": suggestions,
        "strategy": strategy,
        "critique": critique,
        "scenario_branches": scenario_branches,
        "after_action_report": after_action,
    }
