"""
Facts API router.

Provides CRUD endpoints for facts in the knowledge graph.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..dependencies import CurrentUser, DatabaseSession
from ...core.models import KnowledgeScope
from ...core.schemas import FactCreate, FactOut, FactUpdate
from ...core.services import kg as kg_service


router = APIRouter(prefix="/facts", tags=["facts"])


@router.get("", response_model=list[FactOut])
async def list_facts(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: Optional[int] = Query(None, description="Optional session filter."),
    scope: Optional[KnowledgeScope] = Query(None, description="Optional scope filter."),
) -> list[FactOut]:
    """List facts for the current user."""
    facts = await kg_service.list_facts(db, user.id, session_id=session_id, scope=scope)
    return [FactOut.model_validate(fact) for fact in facts]


@router.post("", response_model=FactOut, status_code=status.HTTP_201_CREATED)
async def create_fact(
    req: FactCreate,
    db: DatabaseSession,
    user: CurrentUser,
) -> FactOut:
    """Create a new fact."""
    entity = await kg_service.get_entity(db, req.subject_entity_id, user.id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    fact = await kg_service.create_fact(
        db,
        user.id,
        subject_entity_id=req.subject_entity_id,
        key=req.key,
        value=req.value,
        value_type=req.value_type or "str",
        unit=req.unit,
        scope=req.scope,
        confidence=req.confidence or 1.0,
        provenance=req.provenance,
        source_type=req.source_type,
        source_ref=req.source_ref,
    )
    return FactOut.model_validate(fact)


@router.patch("/{fact_id}", response_model=FactOut)
async def update_fact(
    req: FactUpdate,
    db: DatabaseSession,
    user: CurrentUser,
    fact_id: int,
) -> FactOut:
    """Update an existing fact."""
    fact = await kg_service.get_fact(db, fact_id, user.id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    updated = await kg_service.update_fact(
        db,
        fact,
        key=req.key,
        value=req.value,
        value_type=req.value_type,
        unit=req.unit,
        scope=req.scope,
        confidence=req.confidence,
        provenance=req.provenance,
        source_type=req.source_type,
        source_ref=req.source_ref,
    )
    return FactOut.model_validate(updated)


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(
    db: DatabaseSession,
    user: CurrentUser,
    fact_id: int,
) -> None:
    """Delete a fact."""
    fact = await kg_service.get_fact(db, fact_id, user.id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    await kg_service.delete_fact(db, fact)
    return None

