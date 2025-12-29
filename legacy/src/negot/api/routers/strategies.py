"""
Strategy pack API router.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from ...core.schemas import StrategySummary
from ...core.services import strategies as strategies_service


router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategySummary])
async def list_strategies() -> list[StrategySummary]:
    """List enabled strategies from the strategy pack."""
    summaries = strategies_service.list_strategies_summary()
    return [StrategySummary.model_validate(item) for item in summaries]


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str = Path(..., description="Identifier of the strategy."),
) -> dict:
    """Return a full strategy template."""
    try:
        return strategies_service.get_strategy(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
