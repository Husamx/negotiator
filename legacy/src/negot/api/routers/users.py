"""
User API router.

Provides endpoints for user settings such as subscription tier.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import CurrentUser, DatabaseSession
from ...core.schemas import UserConsentUpdate, UserTierUpdate
from ...core.services import auth as auth_service


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_current_user(user: CurrentUser) -> dict:
    """Return basic user profile information."""
    return {
        "id": user.id,
        "tier": user.tier.value,
        "consent_telemetry": user.consent_telemetry,
        "consent_raw_text": user.consent_raw_text,
    }


@router.patch("/me/tier")
async def update_tier(
    req: UserTierUpdate,
    db: DatabaseSession,
    user: CurrentUser,
) -> dict:
    """Update the user's subscription tier."""
    updated = await auth_service.update_user_tier(db, user, req.tier)
    return {"id": updated.id, "tier": updated.tier.value}


@router.patch("/me/consent")
async def update_consents(
    req: UserConsentUpdate,
    db: DatabaseSession,
    user: CurrentUser,
) -> dict:
    """Update user consent flags."""
    updated = await auth_service.update_user_consents(
        db, user, req.consent_telemetry, req.consent_raw_text
    )
    return {
        "id": updated.id,
        "tier": updated.tier.value,
        "consent_telemetry": updated.consent_telemetry,
        "consent_raw_text": updated.consent_raw_text,
    }
