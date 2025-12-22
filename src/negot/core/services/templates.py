"""
Template selection and management.

Templates define the structure of negotiations. This module provides
LLM-driven selection of the most appropriate template given a topic
description and returns the list of official templates defined in
``docs/REQUIREMENTS.md``.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..events import emit_event
from ..models import EventType, TemplateDraft, TemplateProposal, TemplateProposalStatus
from .llm_utils import acompletion_with_retry, extract_completion_text


class TemplateSelection(BaseModel):
    template_id: str = Field(..., description="Selected template identifier.")
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    rationale: Optional[str] = None


TEMPLATE_SELECTION_PROMPT = """You are the Template Router agent.
Pick the best template_id for the user's topic from the provided list.
If none fit, return template_id = "other".
Output JSON only: {"template_id": "...", "confidence": 0.0-1.0, "rationale": "..."}.
"""


async def select_template(topic_text: str) -> str:
    """Select a template ID using an LLM classifier."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot select template.")
    templates = list_official_templates()
    payload = {"topic_text": topic_text, "templates": templates}
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": TEMPLATE_SELECTION_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
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
        response = await client(response_model=TemplateSelection, **completion_kwargs)
        selection = response
    except Exception:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty template selection.")
        selection = TemplateSelection.model_validate_json(content)
    valid_ids = {template["id"] for template in templates}
    if selection.template_id not in valid_ids:
        raise ValueError(f"Invalid template_id returned: {selection.template_id}")
    return selection.template_id


def list_official_templates() -> List[dict[str, str]]:
    """Return a list of official templates shipped with the MVP.

    Each entry contains an identifier and a human‑readable name. In a
    full implementation this data would come from a database or
    configuration file.
    """
    return [
        {"id": "roommate_conflict", "name": "Roommate conflict"},
        {"id": "relationship_disagreement", "name": "Relationship disagreement"},
        {"id": "dating_expectations", "name": "Dating expectations"},
        {"id": "friendship_conflict", "name": "Friendship conflict"},
        {"id": "money_with_friends", "name": "Money with friends"},
        {"id": "family_parental_disagreement", "name": "Family / parental disagreement"},
        {"id": "workplace_boundary", "name": "Workplace boundary / manager conflict"},
        {"id": "salary_offer", "name": "Salary offer / compensation negotiation"},
        {"id": "rent_renewal", "name": "Rent / lease renewal"},
        {"id": "refund_complaint", "name": "Refund / complaint dispute"},
        {"id": "other", "name": "Other"},
    ]


async def create_template_draft(
    db: AsyncSession,
    user_id: int,
    topic_text: str,
    title: Optional[str] = None,
    payload: Optional[dict] = None,
) -> TemplateDraft:
    draft = TemplateDraft(
        user_id=user_id,
        topic_text=topic_text,
        title=title,
        payload=payload,
    )
    db.add(draft)
    await db.flush()
    await emit_event(
        db,
        EventType.template_draft_generated,
        user_id,
        session_id=None,
        payload={"draft_id": draft.id, "topic_text": topic_text},
    )
    return draft


async def create_template_proposal(
    db: AsyncSession,
    user_id: int,
    payload: dict,
    draft_id: Optional[int] = None,
) -> TemplateProposal:
    proposal = TemplateProposal(
        user_id=user_id,
        draft_id=draft_id,
        payload=payload,
    )
    db.add(proposal)
    await db.flush()
    await emit_event(
        db,
        EventType.template_proposal_submitted,
        user_id,
        session_id=None,
        payload={"proposal_id": proposal.id, "draft_id": draft_id},
    )
    return proposal


async def create_template_proposal_for_other(
    db: AsyncSession, user_id: int, session_id: int, topic_text: str
) -> TemplateProposal:
    payload = {
        "topic_text": topic_text,
        "generated_at": datetime.utcnow().isoformat(),
        "notes": "Auto-generated draft template proposal for an 'other' topic.",
    }
    draft = await create_template_draft(db, user_id, topic_text, title="Other topic", payload=payload)
    proposal = await create_template_proposal(db, user_id, payload=payload, draft_id=draft.id)
    await emit_event(
        db,
        EventType.template_proposal_submitted,
        user_id,
        session_id=session_id,
        payload={"proposal_id": proposal.id, "draft_id": draft.id},
    )
    return proposal


async def list_template_drafts(db: AsyncSession, user_id: int) -> List[TemplateDraft]:
    result = await db.execute(select(TemplateDraft).where(TemplateDraft.user_id == user_id))
    return result.scalars().all()


async def list_template_proposals(db: AsyncSession, user_id: int) -> List[TemplateProposal]:
    result = await db.execute(select(TemplateProposal).where(TemplateProposal.user_id == user_id))
    return result.scalars().all()


async def list_all_template_proposals(db: AsyncSession) -> List[TemplateProposal]:
    result = await db.execute(select(TemplateProposal))
    return result.scalars().all()


async def review_template_proposal(
    db: AsyncSession,
    proposal_id: int,
    decision: str,
    reviewer_notes: Optional[str] = None,
) -> TemplateProposal:
    proposal = await db.get(TemplateProposal, proposal_id)
    if proposal is None:
        raise ValueError("Template proposal not found")
    if decision == "approve":
        proposal.status = TemplateProposalStatus.approved
        event_type = EventType.template_proposal_approved
    elif decision == "reject":
        proposal.status = TemplateProposalStatus.rejected
        event_type = EventType.template_proposal_rejected
    else:
        raise ValueError("Decision must be approve or reject")
    proposal.reviewer_notes = reviewer_notes
    proposal.reviewed_at = datetime.utcnow()
    await db.flush()
    await emit_event(
        db,
        event_type,
        proposal.user_id,
        session_id=None,
        payload={"proposal_id": proposal.id, "reviewer_notes": reviewer_notes},
    )
    return proposal
