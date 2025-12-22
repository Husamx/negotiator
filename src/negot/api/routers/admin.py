"""
Admin review API router.

Provides endpoints for reviewing template proposals.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..dependencies import CurrentUser, DatabaseSession
from ...core.schemas import TemplateProposalOut, TemplateReviewRequest
from ...core.services import templates as templates_service


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/template-proposals", response_model=list[TemplateProposalOut])
async def list_template_proposals(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[TemplateProposalOut]:
    """List all template proposals (admin)."""
    proposals = await templates_service.list_all_template_proposals(db)
    return [TemplateProposalOut.model_validate(proposal) for proposal in proposals]


@router.post("/template-proposals/{proposal_id}/review", response_model=TemplateProposalOut)
async def review_template_proposal(
    req: TemplateReviewRequest,
    db: DatabaseSession,
    user: CurrentUser,
    proposal_id: int,
) -> TemplateProposalOut:
    """Approve or reject a template proposal (admin)."""
    try:
        proposal = await templates_service.review_template_proposal(
            db, proposal_id, decision=req.decision, reviewer_notes=req.reviewer_notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TemplateProposalOut.model_validate(proposal)

