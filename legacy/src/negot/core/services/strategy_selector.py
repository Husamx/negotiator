"""
LLM-based strategy selection.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object
from .conditions import evaluate_condition

logger = logging.getLogger(__name__)

STRATEGY_SELECTION_PROMPT = """You are the Strategy Selection agent.
Choose the best strategies for the user given the CaseSnapshot and strategy metadata.
Return JSON only matching this schema:
{"request":{"case_snapshot":{...},"available_strategy_ids":[...],"max_results":5,"user_intent":"..."},
 "response":{"ranked_strategies":[{"strategy_id":"...","score":0.0,"why":"...","failed_prerequisites":[]}]} }

Rules:
- Use only provided evidence; unknown stays unknown.
- Rank up to max_results strategies.
- Higher score means better fit.
"""


class StrategySelectionRequest(BaseModel):
    case_snapshot: dict
    available_strategy_ids: List[str]
    max_results: int = 5
    user_intent: Optional[str] = None


class RankedStrategy(BaseModel):
    strategy_id: str
    score: float = Field(ge=0.0, le=1.0)
    why: str
    failed_prerequisites: List[str] = Field(default_factory=list)


class StrategySelectionResponse(BaseModel):
    ranked_strategies: List[RankedStrategy]


class StrategySelectionIO(BaseModel):
    request: StrategySelectionRequest
    response: StrategySelectionResponse


def _failed_prereq_ids(strategy: dict, case_snapshot: dict) -> List[str]:
    failed = []
    for prereq in strategy.get("applicability", {}).get("prerequisites", []):
        condition = prereq.get("condition") or {}
        if not evaluate_condition(condition, case_snapshot):
            failed.append(prereq.get("id"))
    return [item for item in failed if item]


def _matches_context(strategy: dict, case_snapshot: dict) -> bool:
    applicability = strategy.get("applicability", {})
    domains = applicability.get("domains", [])
    channels = applicability.get("channels", [])
    if domains and case_snapshot.get("domain") not in domains:
        return False
    if channels and case_snapshot.get("channel") not in channels:
        return False
    return True


async def select_strategies(
    *,
    case_snapshot: dict,
    strategy_metadata: List[dict],
    max_results: int = 5,
    user_intent: Optional[str] = None,
) -> StrategySelectionIO:
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot select strategy.")
    available_ids = [item["strategy_id"] for item in strategy_metadata]
    request_payload = StrategySelectionRequest(
        case_snapshot=case_snapshot,
        available_strategy_ids=available_ids,
        max_results=max_results,
        user_intent=user_intent,
    ).model_dump()
    user_payload = {
        "request": request_payload,
        "strategy_metadata": strategy_metadata,
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": STRATEGY_SELECTION_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        "temperature": 0.2,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    response = await acompletion_with_retry(**completion_kwargs)
    content = extract_completion_text(response)
    if not content:
        raise RuntimeError("LiteLLM returned an empty strategy selection.")
    try:
        selection = StrategySelectionIO.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse strategy selection output. Error: %s", exc)
        extracted = extract_json_object(content)
        if extracted is None:
            raise
        selection = StrategySelectionIO.model_validate(extracted)

    filtered_ranked: List[RankedStrategy] = []
    strategy_by_id = {item["strategy_id"]: item for item in strategy_metadata}
    for ranked in selection.response.ranked_strategies:
        if ranked.strategy_id not in strategy_by_id:
            continue
        strategy = strategy_by_id[ranked.strategy_id]
        if not _matches_context(strategy, case_snapshot):
            continue
        ranked.failed_prerequisites = _failed_prereq_ids(strategy, case_snapshot)
        filtered_ranked.append(ranked)
        if len(filtered_ranked) >= max_results:
            break
    if not filtered_ranked:
        raise RuntimeError("Strategy selection returned no applicable strategies.")
    selection.response.ranked_strategies = filtered_ranked
    return selection
