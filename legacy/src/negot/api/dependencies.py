"""
API dependencies.

This module defines reusable dependencies for FastAPI endpoints. These
functions leverage the dependency injection system to provide a
configured database session and authenticate the current user.
"""
from __future__ import annotations

from typing import Annotated, AsyncIterator, Optional

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db_session
from ..core.services import auth as auth_service
from ..core.models import User


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency that yields a database session."""
    async with get_db_session() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DatabaseSession,
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
) -> User:
    """Dependency that resolves the authenticated user."""
    return await auth_service.get_current_user(db, x_user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
