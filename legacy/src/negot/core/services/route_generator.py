"""
Generate alternative negotiation routes for the canvas tree.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object

logger = logging.getLogger(__name__)

ROUTE_SYSTEM_PROMPT = """You are the Negotiation Route Generator.
Generate ONE plausible counterparty response that represents a distinct path
from existing routes.

Rules:
- Use only provided context; unknown stays unknown.
- The new route must differ in action/logic (objection, concession, trade, delay, counter, etc.), not just wording.
- Keep responses concise (2-4 sentences each).
- Choose an action_label from action_palette.
- If forced_action_label is provided, you MUST use it exactly.
- Variant guidance:
  - LIKELY: most plausible neutral path.
  - RISK: tougher pushback or higher conflict risk.
  - BEST: more cooperative or favorable to the user.
  - ALT: introduce a different trade-off or angle.
- Output JSON only:
{"counterparty_response":"...","action_label":"...","rationale":"..."}
"""


class RouteBranchResult(BaseModel):
    counterparty_response: str = Field(..., min_length=5)
    rationale: str = Field(..., min_length=5)
    action_label: str = Field(..., min_length=3)


SIMILARITY_SYSTEM_PROMPT = """You are a negotiation analyst.
Decide if the candidate counterparty response is too similar to any existing route.

Rules:
- Compare semantics, concessions, demands, and the action taken (not wording overlap).
- If the candidate uses the same action or offers essentially the same deal, it is similar.
- If the candidate introduces a materially different action or trade-off, it is NOT similar.
- Output JSON only:
{"too_similar": true/false, "reason": "..."}
"""


async def _too_similar(
    candidate: RouteBranchResult,
    existing: List[dict],
    settings: Any,
) -> bool:
    if not existing:
        return False
    payload = {
        "candidate": {
            "counterparty_response": candidate.counterparty_response,
            "action_label": candidate.action_label,
            "rationale": candidate.rationale,
        },
        "existing_routes": [
            {
                "counterparty_response": item.get("counterparty_response"),
                "action_label": item.get("action_label"),
                "rationale": item.get("rationale"),
            }
            for item in existing
        ],
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": SIMILARITY_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        "temperature": 0.1,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            return False
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = extract_json_object(content) or {}
        return bool(result.get("too_similar"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Similarity judge failed: %s", exc)
        return False


def _build_action_palette(strategy_context: Optional[dict]) -> List[dict]:
    actions: List[dict] = []
    if strategy_context:
        summary = strategy_context.get("summary") or strategy_context.get("goal")
        if summary:
            actions.append({"label": "Primary move", "instruction": summary})
        for branch in strategy_context.get("branches") or []:
            move = branch.get("recommended_move") or {}
            label = move.get("move_type") or branch.get("label")
            instruction = move.get("instruction") or branch.get("label") or ""
            if label:
                actions.append({"label": label, "instruction": instruction})
    # Deduplicate by label while preserving order
    seen = set()
    unique_actions = []
    for action in actions:
        label = (action.get("label") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        unique_actions.append(action)
    if unique_actions:
        return unique_actions
    return [
        {"label": "Hold line with justification", "instruction": "Reinforce constraints with objective criteria."},
        {"label": "Offer conditional trade-off", "instruction": "Propose give-get terms or contingency."},
        {"label": "Ask calibrated question", "instruction": "Use a how/what question to surface constraints."},
        {"label": "Counteranchor with range", "instruction": "Provide a bounded counteroffer range."},
        {"label": "Defer and schedule", "instruction": "Set a next step and timeline without conceding."},
        {"label": "Request criteria", "instruction": "Ask for decision criteria or process."},
        {"label": "Introduce new issue", "instruction": "Shift to another term or issue area."},
        {"label": "Escalate decision-maker", "instruction": "Clarify authority or escalate."},
        {"label": "Signal boundary", "instruction": "State a firm limit or walk-away condition."},
        {"label": "Propose alternative structure", "instruction": "Reframe the deal structure or package."},
    ]


def _action_conflict(candidate: RouteBranchResult, existing: List[dict]) -> bool:
    if not existing:
        return False
    cand = (candidate.action_label or "").strip().lower()
    if not cand:
        return False
    for item in existing:
        existing_label = (item.get("action_label") or "").strip().lower()
        if existing_label and cand == existing_label:
            return True
    return False


async def generate_route_branch(
    *,
    case_snapshot: dict,
    history: List[Dict[str, str]],
    strategy_context: Optional[dict],
    counterparty_style: Optional[str],
    variant: str,
    existing_routes: Optional[List[dict]] = None,
) -> RouteBranchResult:
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot generate routes.")
    existing_routes = existing_routes or []
    action_palette = _build_action_palette(strategy_context)
    avoid_actions = [
        item.get("action_label") for item in existing_routes if item.get("action_label")
    ]
    forced_action_label = None
    for action in action_palette:
        label = action.get("label")
        if label and label not in avoid_actions:
            forced_action_label = label
            break
    payload = {
        "variant": variant,
        "counterparty_style": counterparty_style,
        "history": history,
        "case_snapshot": case_snapshot,
        "strategy_context": {
            "strategy_id": (strategy_context or {}).get("strategy_id"),
            "name": (strategy_context or {}).get("name"),
            "summary": (strategy_context or {}).get("summary"),
            "goal": (strategy_context or {}).get("goal"),
            "counterparty_guidance": (strategy_context or {}).get("counterparty_guidance", []),
        },
        "action_palette": action_palette,
        "avoid_action_labels": avoid_actions,
        "forced_action_label": forced_action_label,
        "existing_routes": existing_routes,
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        "temperature": 0.4,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url

    def _parse(content: str) -> RouteBranchResult:
        try:
            return RouteBranchResult.model_validate_json(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse route branch output. Error: %s", exc)
            extracted = extract_json_object(content)
            if extracted is None:
                raise
            return RouteBranchResult.model_validate(extracted)

    response = await acompletion_with_retry(**completion_kwargs)
    content = extract_completion_text(response)
    if not content:
        raise RuntimeError("LiteLLM returned an empty route branch.")
    result = _parse(content)

    palette_labels = {
        (a.get("label") or "").strip().lower() for a in action_palette if a.get("label")
    }
    action_invalid = bool(palette_labels) and (
        (result.action_label or "").strip().lower() not in palette_labels
    )
    too_similar = await _too_similar(result, existing_routes, settings)
    if too_similar or _action_conflict(result, existing_routes) or action_invalid:
        completion_kwargs["messages"][0]["content"] = (
            ROUTE_SYSTEM_PROMPT
            + "\nYour previous output was too similar, reused the same action, or used an invalid action label. "
            + "Generate a different action and a logically distinct route."
        )
        completion_kwargs["messages"][1]["content"] = json.dumps(payload, default=str)
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty route branch retry.")
        result = _parse(content)
    return result
