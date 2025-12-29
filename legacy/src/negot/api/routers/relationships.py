"""
Relationships API router.

Provides CRUD endpoints for relationships in the knowledge graph.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..dependencies import CurrentUser, DatabaseSession
from ...core.schemas import RelationshipCreate, RelationshipOut, RelationshipUpdate
from ...core.services import kg as kg_service


router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.get("", response_model=list[RelationshipOut])
async def list_relationships(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[RelationshipOut]:
    """List relationships for the current user."""
    relationships = await kg_service.list_relationships(db, user.id)
    return [RelationshipOut.model_validate(rel) for rel in relationships]


@router.post("", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    req: RelationshipCreate,
    db: DatabaseSession,
    user: CurrentUser,
) -> RelationshipOut:
    """Create a new relationship."""
    src = await kg_service.get_entity(db, req.src_entity_id, user.id)
    dst = await kg_service.get_entity(db, req.dst_entity_id, user.id)
    if src is None or dst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    relationship = await kg_service.create_relationship(
        db,
        user.id,
        src_entity_id=req.src_entity_id,
        rel_type=req.rel_type,
        dst_entity_id=req.dst_entity_id,
        provenance=req.provenance,
    )
    return RelationshipOut.model_validate(relationship)


@router.patch("/{relationship_id}", response_model=RelationshipOut)
async def update_relationship(
    req: RelationshipUpdate,
    db: DatabaseSession,
    user: CurrentUser,
    relationship_id: int,
) -> RelationshipOut:
    """Update an existing relationship."""
    relationship = await kg_service.get_relationship(db, relationship_id, user.id)
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    updated = await kg_service.update_relationship(
        db, relationship, rel_type=req.rel_type, provenance=req.provenance
    )
    return RelationshipOut.model_validate(updated)


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    db: DatabaseSession,
    user: CurrentUser,
    relationship_id: int,
) -> None:
    """Delete a relationship."""
    relationship = await kg_service.get_relationship(db, relationship_id, user.id)
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    await kg_service.delete_relationship(db, relationship)
    return None

