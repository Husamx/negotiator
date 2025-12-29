"""
Template API router.

Provides endpoints for listing official templates. Draft template
management is left for future versions. The list of templates is
hard‑coded in this MVP but would typically be stored in a database.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import CurrentUser, DatabaseSession
from ...core.schemas import TemplateDraftOut, TemplateProposalCreate, TemplateProposalOut
from ...core.services import templates as templates_service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[dict[str, str]])
async def get_templates() -> list[dict[str, str]]:
    """Return the list of official templates."""
    return templates_service.list_official_templates()


@router.get("/drafts", response_model=list[TemplateDraftOut])
async def list_drafts(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[TemplateDraftOut]:
    """List template drafts for the current user."""
    drafts = await templates_service.list_template_drafts(db, user.id)
    return [TemplateDraftOut.model_validate(draft) for draft in drafts]


@router.get("/proposals", response_model=list[TemplateProposalOut])
async def list_proposals(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[TemplateProposalOut]:
    """List template proposals for the current user."""
    proposals = await templates_service.list_template_proposals(db, user.id)
    return [TemplateProposalOut.model_validate(proposal) for proposal in proposals]


@router.post("/proposals", response_model=TemplateProposalOut)
async def submit_proposal(
    req: TemplateProposalCreate,
    db: DatabaseSession,
    user: CurrentUser,
) -> TemplateProposalOut:
    """Submit a template proposal for review."""
    proposal = await templates_service.create_template_proposal(
        db, user.id, payload=req.payload, draft_id=req.draft_id
    )
    return TemplateProposalOut.model_validate(proposal)

