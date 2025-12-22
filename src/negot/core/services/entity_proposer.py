"""
LLM-driven entity proposer for session setup.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object

logger = logging.getLogger(__name__)

MAX_ENTITY_PROPOSALS = 5

ENTITY_PROPOSER_PROMPT = """You are the Entity Proposer agent.
Select the most relevant existing entities to attach to a new session.
Rules:
- Only select from the provided entities.
- Do not include entities already attached.
- Return 0 to 5 entity IDs, ordered by relevance.
- Unknown stays unknown; do not invent entities.
Output JSON only: {"entity_ids":[1,2], "rationale":"..."}.
"""


class EntityProposal(BaseModel):
    entity_ids: List[int] = Field(default_factory=list)
    rationale: Optional[str] = None


async def propose_entities(
    *,
    topic_text: str,
    entities: Sequence[Dict[str, Any]],
    attached_entity_ids: Optional[Sequence[int]] = None,
) -> List[int]:
    """Propose which existing entities to attach for the session."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot propose entities.")
    payload = {
        "topic_text": topic_text,
        "attached_entity_ids": list(attached_entity_ids or []),
        "entities": list(entities),
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": ENTITY_PROPOSER_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
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
        response = await client(response_model=EntityProposal, **completion_kwargs)
        proposal = response
    except Exception as exc:  # noqa: BLE001
        logger.warning("Entity proposer failed. Error: %s", exc)
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty entity proposal.")
        try:
            proposal = EntityProposal.model_validate_json(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse entity proposal. Error: %s", exc)
            extracted = extract_json_object(content)
            if extracted is None:
                raise
            proposal = EntityProposal.model_validate(extracted)
    candidate_ids = {ent.get("id") for ent in entities if ent.get("id") is not None}
    attached_ids = set(attached_entity_ids or [])
    filtered = [
        entity_id
        for entity_id in proposal.entity_ids
        if entity_id in candidate_ids and entity_id not in attached_ids
    ]
    return filtered[:MAX_ENTITY_PROPOSALS]
