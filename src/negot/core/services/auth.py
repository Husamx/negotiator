"""
Authentication and user management service.

In this simplified v0.1 implementation, authentication is rudimentary: the
API expects a header ``X-User-Id`` containing an integer user ID. If the
user does not exist in the database, they will be created automatically
with the default tier (standard) and all consent flags set to false. For
a production system you should integrate a proper identity provider.

All functions in this module should be invoked with an active SQLAlchemy
``AsyncSession`` and should return ORM objects or raise exceptions for
invalid access.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, UserTier


async def get_current_user(
    db: AsyncSession, x_user_id: Optional[int] = Header(default=None, alias="X-User-Id")
) -> User:
    """Retrieve the current authenticated user.

    If the request does not include a valid ``X-User-Id`` header the
    request is rejected. In development environments you might
    customise this behaviour to allow anonymous sessions. New users
    discovered via the header are created on the fly with the
    ``standard`` tier.

    :param db: SQLAlchemy async session.
    :param x_user_id: User ID passed via header.
    :return: The loaded or newly created ``User`` object.
    :raises HTTPException: if no user ID is provided.
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )
    # Try to fetch the user from the database
    user = (await db.execute(select(User).where(User.id == x_user_id))).scalar_one_or_none()
    if user is None:
        # Create a new user with default values
        user = User(id=x_user_id, tier=UserTier.standard)
        db.add(user)
    return user


async def update_user_tier(db: AsyncSession, user: User, tier: UserTier) -> User:
    """Update the user's subscription tier."""
    user.tier = tier
    await db.flush()
    return user


async def update_user_consents(
    db: AsyncSession,
    user: User,
    consent_telemetry: Optional[bool],
    consent_raw_text: Optional[bool],
) -> User:
    """Update user consent flags."""
    if consent_telemetry is not None:
        user.consent_telemetry = consent_telemetry
    if consent_raw_text is not None:
        user.consent_raw_text = consent_raw_text
    await db.flush()
    return user
