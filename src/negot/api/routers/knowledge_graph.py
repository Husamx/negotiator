"""
Knowledge graph API router.

Provides CRUD endpoints for entities in the user's knowledge graph.
Facts and relationships can be added in future versions. See
``docs/API.md`` for the contract outline.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from ..dependencies import CurrentUser, DatabaseSession
from ...core.schemas import EntityCreate, EntityOut, EntityUpdate
from ...core.services import kg as kg_service


router = APIRouter(prefix="/entities", tags=["knowledge_graph"])


@router.get("", response_model=list[EntityOut])
async def list_entities(db: DatabaseSession, user: CurrentUser) -> list[EntityOut]:
    """Return all entities owned by the current user."""
    entities = await kg_service.list_entities(db, user.id)
    return [EntityOut.model_validate(e) for e in entities]


@router.post("", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
async def create_entity(req: EntityCreate, db: DatabaseSession, user: CurrentUser) -> EntityOut:
    """Create a new entity."""
    entity = await kg_service.create_entity(db, user.id, req.type, req.name, req.attributes)
    return EntityOut.model_validate(entity)


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    db: DatabaseSession,
    user: CurrentUser,
    entity_id: int = Path(..., description="ID of the entity."),
) -> EntityOut:
    """Retrieve an entity by its ID."""
    entity = await kg_service.get_entity(db, entity_id, user.id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return EntityOut.model_validate(entity)


@router.patch("/{entity_id}", response_model=EntityOut)
async def update_entity(
    req: EntityUpdate,
    db: DatabaseSession,
    user: CurrentUser,
    entity_id: int = Path(..., description="ID of the entity to update."),
) -> EntityOut:
    """Update an entity's fields."""
    entity = await kg_service.get_entity(db, entity_id, user.id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    updated = await kg_service.update_entity(db, entity, req.name, req.attributes)
    return EntityOut.model_validate(updated)


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    db: DatabaseSession,
    user: CurrentUser,
    entity_id: int = Path(..., description="ID of the entity to delete."),
) -> None:
    """Delete an entity and all related facts and relationships."""
    entity = await kg_service.get_entity(db, entity_id, user.id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    await kg_service.delete_entity(db, entity)
    return None

