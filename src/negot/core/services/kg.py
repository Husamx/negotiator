"""
Knowledge graph service for CRUD operations on entities, facts and relationships.

This module encapsulates database interactions related to the world graph and
the epistemic model. Higher‑level services and API routers should use
these functions rather than interacting with the ORM directly.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import emit_event
from ..models import (
    Entity,
    Fact,
    EventType,
    KnowledgeEdge,
    KnowledgeScope,
    KnowledgeStatus,
    KnowledgeSource,
    Relationship,
    Session,
    SessionEntity,
)


async def list_entities(db: AsyncSession, user_id: int) -> List[Entity]:
    """Return all entities owned by the user."""
    result = await db.execute(select(Entity).where(Entity.user_id == user_id))
    return result.scalars().all()


async def create_entity(db: AsyncSession, user_id: int, ent_type: str, name: str, attributes: Optional[dict] = None) -> Entity:
    """Create a new entity for the given user."""
    entity = Entity(user_id=user_id, type=ent_type, name=name, attributes=attributes or {})
    db.add(entity)
    await db.flush()  # assign ID
    await emit_event(
        db,
        EventType.entity_created,
        user_id,
        session_id=None,
        payload={"entity_id": entity.id, "type": ent_type, "name": name},
    )
    return entity


async def get_entity(db: AsyncSession, entity_id: int, user_id: int) -> Optional[Entity]:
    """Return an entity by ID if owned by the user."""
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.user_id == user_id))
    return result.scalar_one_or_none()


async def get_fact(db: AsyncSession, fact_id: int, user_id: int) -> Optional[Fact]:
    """Return a fact by ID if owned by the user."""
    result = await db.execute(select(Fact).where(Fact.id == fact_id, Fact.user_id == user_id))
    return result.scalar_one_or_none()


async def get_relationship(db: AsyncSession, relationship_id: int, user_id: int) -> Optional[Relationship]:
    """Return a relationship by ID if owned by the user."""
    result = await db.execute(
        select(Relationship).where(Relationship.id == relationship_id, Relationship.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_knowledge_edge(db: AsyncSession, edge_id: int, user_id: int) -> Optional[KnowledgeEdge]:
    """Return a knowledge edge by ID if owned by the user."""
    result = await db.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.id == edge_id, KnowledgeEdge.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_entity(db: AsyncSession, entity: Entity, name: Optional[str] = None, attributes: Optional[dict] = None) -> Entity:
    """Update the given entity's fields."""
    if name is not None:
        entity.name = name
    if attributes is not None:
        entity.attributes = attributes
    await db.flush()
    await emit_event(
        db,
        EventType.entity_edited,
        entity.user_id,
        session_id=None,
        payload={"entity_id": entity.id},
    )
    return entity


async def delete_entity(db: AsyncSession, entity: Entity) -> None:
    """Delete an entity and cascade related objects."""
    await db.delete(entity)
    await emit_event(
        db,
        EventType.entity_deleted,
        entity.user_id,
        session_id=None,
        payload={"entity_id": entity.id},
    )


async def attach_entities_to_session(db: AsyncSession, session: Session, entities: Iterable[Entity]) -> None:
    """Associate a set of entities with a session."""
    for entity in entities:
        session.attached_entities.append(entity)
    await db.flush()


async def compute_visible_facts(
    db: AsyncSession, session: Session, counterparty_entity_id: Optional[int] = None
) -> List[dict]:
    """Compute facts visible to the counterparty in a session.

    For the MVP we consider that all facts attached to the session's
    entities and marked as global scope are visible. A more complete
    implementation would consider knowledge edges and priors.
    """
    result = await db.execute(
        select(SessionEntity.entity_id).where(SessionEntity.session_id == session.id)
    )
    entity_ids = result.scalars().all()
    if not entity_ids:
        return []
    result = await db.execute(
        select(Fact).where(
            Fact.subject_entity_id.in_(entity_ids), Fact.scope == KnowledgeScope.global_scope
        )
    )
    facts = result.scalars().all()
    return [
        {
            "id": f.id,
            "subject_entity_id": f.subject_entity_id,
            "key": f.key,
            "value": f.value,
            "scope": f.scope,
        }
        for f in facts
    ]


async def commit_facts(
    db: AsyncSession,
    session: Session,
    decisions: List[dict],
    user_id: int,
) -> List[Fact]:
    """Persist candidate facts according to memory review decisions.

    This function changes the scope of facts from session-only to global
    based on the user's choices. Facts marked as ``discard`` are deleted.
    """
    committed: List[Fact] = []
    for decision in decisions:
        fact_id = decision.get("fact_id")
        action = decision.get("decision")
        if fact_id is None or action not in {"save_global", "save_session_only", "discard"}:
            continue
        fact = await db.get(Fact, fact_id)
        if not fact or fact.user_id != user_id:
            continue
        if action == "discard":
            await db.delete(fact)
            continue
        if action == "save_global":
            fact.scope = KnowledgeScope.global_scope
        committed.append(fact)
    await db.flush()
    return committed


async def list_facts(
    db: AsyncSession, user_id: int, session_id: Optional[int] = None, scope: Optional[KnowledgeScope] = None
) -> List[Fact]:
    """Return facts for a user, optionally filtered by session or scope."""
    query = select(Fact).where(Fact.user_id == user_id)
    if session_id is not None:
        query = query.where(Fact.session_id == session_id)
    if scope is not None:
        query = query.where(Fact.scope == scope)
    result = await db.execute(query)
    return result.scalars().all()


async def create_fact(
    db: AsyncSession,
    user_id: int,
    subject_entity_id: int,
    key: str,
    value: str,
    value_type: str = "str",
    unit: Optional[str] = None,
    scope: KnowledgeScope = KnowledgeScope.global_scope,
    confidence: float = 1.0,
    provenance: Optional[dict] = None,
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> Fact:
    """Create a fact for the given user."""
    fact = Fact(
        user_id=user_id,
        subject_entity_id=subject_entity_id,
        key=key,
        value=value,
        value_type=value_type,
        unit=unit,
        scope=scope,
        confidence=confidence,
        provenance=provenance,
        source_type=source_type,
        source_ref=source_ref,
    )
    db.add(fact)
    await db.flush()
    await emit_event(
        db,
        EventType.fact_confirmed if scope == KnowledgeScope.global_scope else EventType.fact_extracted,
        user_id,
        session_id=fact.session_id,
        payload={"fact_id": fact.id, "scope": fact.scope.value if hasattr(fact.scope, "value") else fact.scope},
    )
    return fact


async def update_fact(
    db: AsyncSession,
    fact: Fact,
    key: Optional[str] = None,
    value: Optional[str] = None,
    value_type: Optional[str] = None,
    unit: Optional[str] = None,
    scope: Optional[KnowledgeScope] = None,
    confidence: Optional[float] = None,
    provenance: Optional[dict] = None,
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> Fact:
    """Update a fact."""
    if key is not None:
        fact.key = key
    if value is not None:
        fact.value = value
    if value_type is not None:
        fact.value_type = value_type
    if unit is not None:
        fact.unit = unit
    if scope is not None:
        fact.scope = scope
    if confidence is not None:
        fact.confidence = confidence
    if provenance is not None:
        fact.provenance = provenance
    if source_type is not None:
        fact.source_type = source_type
    if source_ref is not None:
        fact.source_ref = source_ref
    await db.flush()
    await emit_event(
        db,
        EventType.fact_confirmed if fact.scope == KnowledgeScope.global_scope else EventType.fact_suggested,
        fact.user_id,
        session_id=fact.session_id,
        payload={"fact_id": fact.id},
    )
    return fact


async def delete_fact(db: AsyncSession, fact: Fact) -> None:
    """Delete a fact."""
    await db.delete(fact)
    await emit_event(
        db,
        EventType.fact_rejected,
        fact.user_id,
        session_id=fact.session_id,
        payload={"fact_id": fact.id},
    )


async def list_relationships(db: AsyncSession, user_id: int) -> List[Relationship]:
    """Return all relationships owned by a user."""
    result = await db.execute(select(Relationship).where(Relationship.user_id == user_id))
    return result.scalars().all()


async def create_relationship(
    db: AsyncSession,
    user_id: int,
    src_entity_id: int,
    rel_type: str,
    dst_entity_id: int,
    provenance: Optional[dict] = None,
) -> Relationship:
    """Create a relationship."""
    relationship = Relationship(
        user_id=user_id,
        src_entity_id=src_entity_id,
        rel_type=rel_type,
        dst_entity_id=dst_entity_id,
        provenance=provenance,
    )
    db.add(relationship)
    await db.flush()
    await emit_event(
        db,
        EventType.relationship_created,
        user_id,
        session_id=None,
        payload={"relationship_id": relationship.id},
    )
    return relationship


async def update_relationship(
    db: AsyncSession,
    relationship: Relationship,
    rel_type: Optional[str] = None,
    provenance: Optional[dict] = None,
) -> Relationship:
    """Update a relationship."""
    if rel_type is not None:
        relationship.rel_type = rel_type
    if provenance is not None:
        relationship.provenance = provenance
    await db.flush()
    await emit_event(
        db,
        EventType.relationship_created,
        relationship.user_id,
        session_id=None,
        payload={"relationship_id": relationship.id, "action": "updated"},
    )
    return relationship


async def delete_relationship(db: AsyncSession, relationship: Relationship) -> None:
    """Delete a relationship."""
    await db.delete(relationship)
    await emit_event(
        db,
        EventType.relationship_deleted,
        relationship.user_id,
        session_id=None,
        payload={"relationship_id": relationship.id},
    )


async def list_knowledge_edges(db: AsyncSession, user_id: int) -> List[KnowledgeEdge]:
    """Return knowledge edges for a user."""
    result = await db.execute(select(KnowledgeEdge).where(KnowledgeEdge.user_id == user_id))
    return result.scalars().all()


async def create_knowledge_edge(
    db: AsyncSession,
    user_id: int,
    knower_entity_id: int,
    fact_id: int,
    status: KnowledgeStatus,
    confidence: float,
    source: KnowledgeSource,
    scope: KnowledgeScope = KnowledgeScope.global_scope,
) -> KnowledgeEdge:
    """Create a knowledge edge."""
    edge = KnowledgeEdge(
        user_id=user_id,
        knower_entity_id=knower_entity_id,
        fact_id=fact_id,
        status=status,
        confidence=confidence,
        source=source,
        scope=scope,
    )
    db.add(edge)
    await db.flush()
    await emit_event(
        db,
        EventType.knowledge_edge_seeded,
        user_id,
        session_id=None,
        payload={"knowledge_edge_id": edge.id},
    )
    return edge


async def update_knowledge_edge(
    db: AsyncSession,
    edge: KnowledgeEdge,
    status: Optional[KnowledgeStatus] = None,
    confidence: Optional[float] = None,
    source: Optional[KnowledgeSource] = None,
    scope: Optional[KnowledgeScope] = None,
) -> KnowledgeEdge:
    """Update a knowledge edge."""
    if status is not None:
        edge.status = status
    if confidence is not None:
        edge.confidence = confidence
    if source is not None:
        edge.source = source
    if scope is not None:
        edge.scope = scope
    await db.flush()
    await emit_event(
        db,
        EventType.knowledge_edge_updated,
        edge.user_id,
        session_id=None,
        payload={"knowledge_edge_id": edge.id},
    )
    return edge


async def delete_knowledge_edge(db: AsyncSession, edge: KnowledgeEdge) -> None:
    """Delete a knowledge edge."""
    await db.delete(edge)
    await emit_event(
        db,
        EventType.knowledge_edge_updated,
        edge.user_id,
        session_id=None,
        payload={"knowledge_edge_id": edge.id, "deleted": True},
    )
