"""
Strategy selection and execution services with persistence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import emit_event
from ..models import EventType, Session, StrategyExecution, StrategySelection
from .conditions import _get_path_value
from .strategy_executor import execute_strategy
from .strategy_packs import (
    list_strategy_summaries,
    load_rubric,
    load_strategy,
    pack_info,
    get_strategy_summary,
)
from .strategy_selector import select_strategies


def _resolve_inputs(strategy: dict, inputs: dict, case_snapshot: dict) -> dict:
    resolved = {}
    missing = []
    for item in strategy.get("inputs", []):
        key = item.get("key")
        if not key:
            continue
        if key in inputs:
            resolved[key] = inputs[key]
            continue
        bind_path = item.get("bind_to_case_path")
        if bind_path:
            exists, value = _get_path_value(case_snapshot, bind_path)
            if exists and value is not None:
                resolved[key] = value
                continue
        if "default" in item:
            resolved[key] = item.get("default")
            continue
        if item.get("required"):
            missing.append(key)
    if missing:
        raise ValueError(f"Missing required strategy inputs: {', '.join(missing)}")
    return resolved


async def run_strategy_selection(
    db: AsyncSession,
    session: Session,
    case_snapshot: dict,
    user_intent: Optional[str] = None,
) -> StrategySelection:
    strategy_metadata = list_strategy_summaries(enabled_only=True)
    selection = await select_strategies(
        case_snapshot=case_snapshot,
        strategy_metadata=strategy_metadata,
        max_results=5,
        user_intent=user_intent,
    )
    ranked = sorted(
        selection.response.ranked_strategies, key=lambda item: item.score, reverse=True
    )
    selection.response.ranked_strategies = ranked
    selected_strategy_id = ranked[0].strategy_id
    pack = pack_info()
    selection_record = StrategySelection(
        session_id=session.id,
        strategy_pack_id=pack.get("pack_id") or "CORE",
        strategy_pack_version=pack.get("pack_version"),
        selected_strategy_id=selected_strategy_id,
        selection_payload=selection.model_dump(),
        created_at=datetime.utcnow(),
    )
    db.add(selection_record)
    await db.flush()
    await emit_event(
        db,
        EventType.strategy_selection_run,
        session.user_id,
        session_id=session.id,
        payload={"selected_strategy_id": selected_strategy_id},
    )
    await emit_event(
        db,
        EventType.strategy_selected,
        session.user_id,
        session_id=session.id,
        payload={"strategy_id": selected_strategy_id},
    )
    return selection_record


async def get_latest_strategy_selection(
    db: AsyncSession, session_id: int
) -> Optional[StrategySelection]:
    result = await db.execute(
        select(StrategySelection)
        .where(StrategySelection.session_id == session_id)
        .order_by(desc(StrategySelection.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_strategy_execution(
    db: AsyncSession, session_id: int
) -> Optional[StrategyExecution]:
    result = await db.execute(
        select(StrategyExecution)
        .where(StrategyExecution.session_id == session_id)
        .order_by(desc(StrategyExecution.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def execute_strategy_for_session(
    db: AsyncSession,
    session: Session,
    case_snapshot: dict,
    strategy_id: str,
    inputs: dict,
) -> StrategyExecution:
    strategy = load_strategy(strategy_id)
    resolved_inputs = _resolve_inputs(strategy, inputs, case_snapshot)
    rubric_ids = strategy.get("evaluation", {}).get("rubric_ids", [])
    rubrics = [load_rubric(rubric_id) for rubric_id in rubric_ids]
    execution = await execute_strategy(
        case_snapshot=case_snapshot,
        strategy=strategy,
        inputs=resolved_inputs,
        rubrics=rubrics,
    )
    execution_record = StrategyExecution(
        session_id=session.id,
        strategy_id=strategy_id,
        strategy_revision=strategy.get("revision", 1),
        inputs=resolved_inputs,
        artifacts=execution.artifacts,
        case_patches=execution.case_patches,
        judge_outputs=execution.judge_outputs,
        trace=execution.trace,
    )
    db.add(execution_record)
    await db.flush()
    model_request = (execution.trace or {}).get("model_request")
    model_response = (execution.trace or {}).get("model_response")
    model_output_raw = (execution.trace or {}).get("model_output_raw")
    await emit_event(
        db,
        EventType.strategy_execution_run,
        session.user_id,
        session_id=session.id,
        payload={
            "strategy_id": strategy_id,
            "model_request": model_request,
        },
    )
    await emit_event(
        db,
        EventType.strategy_execution_completed,
        session.user_id,
        session_id=session.id,
        payload={
            "strategy_id": strategy_id,
            "model_request": model_request,
            "model_response": model_response,
            "model_output_raw": model_output_raw,
        },
    )
    return execution_record


def list_strategies_summary() -> List[dict]:
    return list_strategy_summaries(enabled_only=True)


def get_strategy(strategy_id: str) -> dict:
    return load_strategy(strategy_id)


def get_strategy_metadata(strategy_id: str) -> dict:
    return get_strategy_summary(strategy_id)
