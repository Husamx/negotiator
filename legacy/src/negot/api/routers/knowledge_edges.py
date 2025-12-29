"""
Knowledge edges API router.

Provides CRUD endpoints for visibility/epistemic edges.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..dependencies import CurrentUser, DatabaseSession
from ...core.models import UserTier
from ...core.schemas import KnowledgeEdgeCreate, KnowledgeEdgeOut, KnowledgeEdgeUpdate
from ...core.services import kg as kg_service


router = APIRouter(prefix="/knowledge-edges", tags=["knowledge_edges"])


def _ensure_premium(user: CurrentUser) -> None:
    if user.tier != UserTier.premium:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Premium required")


@router.get("", response_model=list[KnowledgeEdgeOut])
async def list_knowledge_edges(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[KnowledgeEdgeOut]:
    """List knowledge edges for the current user."""
    edges = await kg_service.list_knowledge_edges(db, user.id)
    return [KnowledgeEdgeOut.model_validate(edge) for edge in edges]


@router.post("", response_model=KnowledgeEdgeOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_edge(
    req: KnowledgeEdgeCreate,
    db: DatabaseSession,
    user: CurrentUser,
) -> KnowledgeEdgeOut:
    """Create a knowledge edge (premium only)."""
    _ensure_premium(user)
    edge = await kg_service.create_knowledge_edge(
        db,
        user.id,
        knower_entity_id=req.knower_entity_id,
        fact_id=req.fact_id,
        status=req.status,
        confidence=req.confidence or 1.0,
        source=req.source,
        scope=req.scope,
    )
    return KnowledgeEdgeOut.model_validate(edge)


@router.patch("/{edge_id}", response_model=KnowledgeEdgeOut)
async def update_knowledge_edge(
    req: KnowledgeEdgeUpdate,
    db: DatabaseSession,
    user: CurrentUser,
    edge_id: int,
) -> KnowledgeEdgeOut:
    """Update a knowledge edge (premium only)."""
    _ensure_premium(user)
    edge = await kg_service.get_knowledge_edge(db, edge_id, user.id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge edge not found")
    updated = await kg_service.update_knowledge_edge(
        db,
        edge,
        status=req.status,
        confidence=req.confidence,
        source=req.source,
        scope=req.scope,
    )
    return KnowledgeEdgeOut.model_validate(updated)


@router.delete("/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_edge(
    db: DatabaseSession,
    user: CurrentUser,
    edge_id: int,
) -> None:
    """Delete a knowledge edge (premium only)."""
    _ensure_premium(user)
    edge = await kg_service.get_knowledge_edge(db, edge_id, user.id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge edge not found")
    await kg_service.delete_knowledge_edge(db, edge)
    return None

