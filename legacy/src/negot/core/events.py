"""
Event logging utilities.

This module centralises the logic for emitting events to the database. Events
are append-only records describing notable actions in the application
such as session creation, messages exchanged or web grounding being
triggered. See ``docs/legacy/EVENTS.md`` for a full taxonomy of event types.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Event, EventType


async def emit_event(
    session: AsyncSession,
    event_type: EventType,
    user_id: int,
    session_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Event:
    """Persist an event record in the database.

    :param session: SQLAlchemy async session to use for DB operations.
    :param event_type: The type of the event being emitted.
    :param user_id: Identifier for the user associated with the event.
    :param session_id: Identifier for the session associated with the event.
    :param payload: Arbitrary JSON-serialisable dictionary with event details.
    :return: The created Event instance.
    """
    event = Event(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(event)
    # Let the caller handle commit/rollback
    return event