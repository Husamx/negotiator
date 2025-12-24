"""
Session API router.

Defines endpoints for creating sessions, posting messages, ending sessions
and committing memory review decisions. See ``docs/API.md`` for the
contract outline.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse

from ..dependencies import CurrentUser, DatabaseSession
from ...core.services import sessions as sessions_service
from ...core.schemas import (
    CaseSnapshotOut,
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionResponse,
    GroundingRequest,
    GroundingResponse,
    IntakeSubmitRequest,
    IntakeSubmitResponse,
    MemoryReviewRequest,
    MemoryReviewResponse,
    PostMessageRequest,
    SessionAttachRequest,
    SessionDetail,
    SessionEventOut,
    SessionSummary,
    SessionUpdateRequest,
    FactOut,
    StrategyExecutionOut,
    StrategyExecutionRequest,
    StrategySelectionOut,
)


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    db: DatabaseSession,
    user: CurrentUser,
) -> list[SessionSummary]:
    """List sessions for the current user."""
    return await sessions_service.list_sessions(db, user)


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    req: CreateSessionRequest,
    db: DatabaseSession,
    user: CurrentUser,
) -> CreateSessionResponse:
    """Create a new negotiation session."""
    return await sessions_service.create_session(db, user, req)


@router.post("/{session_id}/messages")
async def post_message(
    req: PostMessageRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> StreamingResponse:
    """Post a message to a session and stream the next turn via SSE."""
    return StreamingResponse(
        sessions_service.stream_message(db, user, session_id, req),
        media_type="text/event-stream",
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> SessionDetail:
    """Get a session detail view."""
    return await sessions_service.get_session_detail(db, user, session_id)


@router.patch("/{session_id}", response_model=SessionDetail)
async def update_session(
    req: SessionUpdateRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> SessionDetail:
    """Update session metadata such as title or counterparty style."""
    return await sessions_service.update_session(db, user, session_id, req)


@router.post("/{session_id}/attach", status_code=204)
async def attach_entities(
    req: SessionAttachRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> None:
    """Attach entities to the session."""
    await sessions_service.attach_entities(db, user, session_id, req.entity_ids)
    return None


@router.post("/{session_id}/detach", status_code=204)
async def detach_entities(
    req: SessionAttachRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> None:
    """Detach entities from the session."""
    await sessions_service.detach_entities(db, user, session_id, req.entity_ids)
    return None


@router.get("/{session_id}/facts", response_model=list[FactOut])
async def list_session_facts(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> list[FactOut]:
    """List session-only facts for memory review."""
    facts = await sessions_service.list_session_facts(db, user, session_id)
    return [FactOut.model_validate(fact) for fact in facts]


@router.get("/{session_id}/events", response_model=list[SessionEventOut])
async def list_session_events(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> list[SessionEventOut]:
    """List events for debugging and orchestration tracing."""
    events = await sessions_service.list_session_events(db, user, session_id)
    return [SessionEventOut.model_validate(event) for event in events]


@router.get("/{session_id}/case-snapshot", response_model=CaseSnapshotOut)
async def get_case_snapshot(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> CaseSnapshotOut:
    """Get the current case snapshot for the session."""
    snapshot = await sessions_service.get_case_snapshot_detail(db, user, session_id)
    return CaseSnapshotOut.model_validate(snapshot)


@router.post("/{session_id}/intake", response_model=IntakeSubmitResponse)
async def submit_intake(
    req: IntakeSubmitRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> IntakeSubmitResponse:
    """Apply intake answers to the case snapshot and run strategy selection."""
    snapshot, selection = await sessions_service.submit_intake(
        db,
        user,
        session_id,
        req.questions,
        req.answers,
        req.summary,
    )
    selection_payload = None
    if selection:
        selection_payload = dict(selection.selection_payload)
        selection_payload["selected_strategy_id"] = selection.selected_strategy_id
    return IntakeSubmitResponse(
        case_snapshot=CaseSnapshotOut.model_validate(snapshot),
        strategy_selection=selection_payload,
    )


@router.get("/{session_id}/strategy/selection", response_model=StrategySelectionOut)
async def get_strategy_selection(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> StrategySelectionOut:
    """Get the latest strategy selection output for the session."""
    selection = await sessions_service.get_strategy_selection(db, user, session_id)
    if selection is None:
        raise HTTPException(status_code=404, detail="Strategy selection not found.")
    return StrategySelectionOut(
        selected_strategy_id=selection.selected_strategy_id,
        selection_payload=selection.selection_payload,
        strategy_pack_id=selection.strategy_pack_id,
        strategy_pack_version=selection.strategy_pack_version,
        created_at=selection.created_at,
    )


@router.post("/{session_id}/strategy/selection", response_model=StrategySelectionOut)
async def run_strategy_selection(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> StrategySelectionOut:
    """Ensure a strategy selection exists for the session."""
    selection = await sessions_service.run_strategy_selection_for_session(
        db, user, session_id, user_intent=None
    )
    return StrategySelectionOut(
        selected_strategy_id=selection.selected_strategy_id,
        selection_payload=selection.selection_payload,
        strategy_pack_id=selection.strategy_pack_id,
        strategy_pack_version=selection.strategy_pack_version,
        created_at=selection.created_at,
    )


@router.post("/{session_id}/strategy/execute", response_model=StrategyExecutionOut)
async def execute_strategy(
    req: StrategyExecutionRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> StrategyExecutionOut:
    """Execute the selected (or provided) strategy."""
    execution = await sessions_service.execute_strategy(
        db,
        user,
        session_id,
        req.strategy_id,
        req.inputs,
    )
    return StrategyExecutionOut.model_validate(execution)


@router.post("/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session to end."),
) -> EndSessionResponse:
    """End a session and return a recap."""
    return await sessions_service.end_session(db, user, session_id)


@router.post("/{session_id}/memory-review", response_model=MemoryReviewResponse)
async def memory_review(
    req: MemoryReviewRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> MemoryReviewResponse:
    """Commit facts after memory review."""
    return await sessions_service.commit_memory_review(db, user, session_id, req)


@router.post("/{session_id}/grounding", response_model=GroundingResponse)
async def explicit_grounding(
    req: GroundingRequest,
    db: DatabaseSession,
    user: CurrentUser,
    session_id: int = Path(..., description="Identifier of the session."),
) -> GroundingResponse:
    """Trigger explicit web grounding for a session."""
    grounding_pack, sources, budget = await sessions_service.explicit_grounding(
        db, user, session_id, req
    )
    return GroundingResponse(grounding_pack=grounding_pack, sources=sources, budget_spent=budget)

