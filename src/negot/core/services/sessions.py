"""
Session management service.

Contains functions to create sessions, post messages, end sessions and
perform memory review. It composes lower‑level services such as the
template selector, web grounding and orchestrator to implement the
per‑turn workflow described in ``docs/ARCHITECTURE.md``.
"""
from __future__ import annotations

import enum
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import orjson
from pydantic import BaseModel, Field

from fastapi import HTTPException, status
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..events import emit_event
from ..models import (
    Entity,
    EventType,
    CaseSnapshot,
    Message,
    MessageThread,
    MessageRole,
    Session,
    SessionEntity,
    StrategyExecution,
    StrategySelection,
    Message as MessageModel,
    User,
    Fact,
    KnowledgeScope,
    UserTier,
)
from ..schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionResponse,
    GroundingRequest,
    MemoryReviewRequest,
    MemoryReviewResponse,
    PostMessageRequest,
    SessionDetail,
    SessionMessageOut,
    SessionSummary,
    SessionUpdateRequest,
    EntityOut,
)
from .case_snapshots import (
    apply_case_patches,
    get_case_snapshot,
    get_or_create_case_snapshot,
    update_case_snapshot_from_intake,
    update_case_snapshot_from_message,
)
from .kg import attach_entities_to_session, commit_facts, compute_visible_facts, list_entities
from .orchestrator import (
    extract_candidate_facts,
    generate_roleplay_stream,
    run_orchestration,
)
from .question_planner import generate_intake_questions
from .strategies import (
    execute_strategy_for_session,
    get_latest_strategy_execution as fetch_latest_strategy_execution,
    get_latest_strategy_selection,
    get_strategy,
    list_strategies_summary,
    run_strategy_selection,
)
from .strategy_packs import validate_case_snapshot
from .route_generator import generate_route_branch
from .entity_proposer import propose_entities
from .templates import create_template_proposal_for_other, select_template
from .web_grounding import need_search, plan_queries, run_search, synthesize
from .llm_utils import acompletion_with_retry, extract_completion_text

ROLEPLAY_HISTORY_LIMIT = 12
DEFAULT_INTAKE_QUESTIONS = [
    "What outcome are you aiming for?",
    "What constraints or limits have they stated?",
    "Are there other terms you can trade (timing, scope, bonuses, etc.)?",
]

logger = logging.getLogger(__name__)


class SessionRecapResult(BaseModel):
    recap: str = Field(..., description="Descriptive recap of the session.")
    after_action_report: Optional[str] = Field(None, description="Premium coaching summary.")


async def _generate_session_title(
    topic_text: Optional[str],
    template_id: Optional[str],
    channel: Optional[str],
) -> str:
    if not topic_text:
        return "Negotiation Session"
    settings = get_settings()
    if not settings.litellm_model:
        return topic_text.strip()[:80]
    system_prompt = (
        "You are a naming assistant for negotiation sessions. "
        "Generate a short, specific title (3-6 words, max 60 characters). "
        "No quotes, no trailing punctuation. Output plain text only."
    )
    payload = {
        "topic_text": topic_text,
        "template_id": template_id,
        "channel": channel,
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        "temperature": 0.3,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            return topic_text.strip()[:80]
        title = content.strip().strip('"').strip("'")
        if len(title) > 80:
            title = title[:80]
        return title or topic_text.strip()[:80]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session title generation failed: %s", exc)
        return topic_text.strip()[:80]


async def create_session(
    db: AsyncSession,
    user: User,
    req: CreateSessionRequest,
) -> CreateSessionResponse:
    """Create a new negotiation session for a user."""
    template_id = await select_template(req.topic_text)
    title = await _generate_session_title(req.topic_text, template_id, req.channel)
    session = Session(
        user_id=user.id,
        template_id=template_id,
        title=title or "Negotiation Session",
        topic_text=req.topic_text,
        counterparty_style=req.counterparty_style,
    )
    db.add(session)
    await db.flush()
    thread = MessageThread(session_id=session.id)
    db.add(thread)
    await db.flush()
    session.active_thread_id = thread.id
    # Attach pre-existing entities if provided
    attached_entities: List[Entity] = []
    if req.attached_entity_ids:
        # Fetch entities by ID and ownership
        for eid in req.attached_entity_ids:
            entity = await db.get(Entity, eid)
            # Only attach if the entity exists and belongs to the user
            if entity and getattr(entity, "user_id", None) == user.id:
                attached_entities.append(entity)
        await attach_entities_to_session(db, session, attached_entities)
    # Emit events
    await emit_event(db, EventType.session_created, user.id, session_id=session.id, payload={"template_id": template_id})
    await emit_event(
        db,
        EventType.session_template_selected,
        user.id,
        session_id=session.id,
        payload={"template_id": template_id},
    )
    if template_id == "other":
        await emit_event(db, EventType.template_other_triggered, user.id, session_id=session.id, payload={"topic": req.topic_text})
        await create_template_proposal_for_other(db, user.id, session.id, req.topic_text)
    # Create initial case snapshot for strategy selection/execution
    case_snapshot = await get_or_create_case_snapshot(db, session, req.channel)
    # Build minimal intake questions based on template + strategy context
    attached_entities_state = [
        {"id": entity.id, "name": entity.name, "type": entity.type}
        for entity in attached_entities
    ]
    strategy_summaries = list_strategies_summary()
    intake_questions = await generate_intake_questions(
        topic_text=req.topic_text,
        template_id=template_id,
        counterparty_style=req.counterparty_style,
        attached_entities=attached_entities_state,
        history=[],
        channel=case_snapshot.payload.get("channel"),
        domain=case_snapshot.payload.get("domain"),
        strategy_summaries=strategy_summaries,
    )
    if not intake_questions:
        intake_questions = DEFAULT_INTAKE_QUESTIONS.copy()
    updated_payload = dict(case_snapshot.payload)
    updated_payload["intake"] = {
        "questions": intake_questions,
        "answers": {},
        "summary": None,
    }
    updated_payload["updated_at"] = datetime.utcnow().isoformat()
    try:
        validate_case_snapshot(updated_payload)
        case_snapshot.payload = updated_payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("Case snapshot validation failed after intake questions: %s", exc)
    await db.flush()
    if not intake_questions:
        try:
            await run_strategy_selection(
                db,
                session,
                case_snapshot.payload,
                user_intent=req.topic_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Strategy selection failed after empty intake: %s", exc)
    all_entities = await list_entities(db, user.id)
    entity_payloads = [
        {
            "id": entity.id,
            "name": entity.name,
            "type": entity.type,
            "attributes": entity.attributes,
        }
        for entity in all_entities
    ]
    proposed_entity_ids = await propose_entities(
        topic_text=req.topic_text,
        entities=entity_payloads,
        attached_entity_ids=req.attached_entity_ids or [],
    )
    proposed_entities = [entity for entity in all_entities if entity.id in proposed_entity_ids]
    return CreateSessionResponse(
        session_id=session.id,
        template_id=template_id,
        proposed_entities=proposed_entities,
        intake_questions=intake_questions,
    )


async def _get_session_or_404(db: AsyncSession, session_id: int, user_id: int) -> Session:
    session = await db.get(Session, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _fetch_attached_entity_ids(db: AsyncSession, session_id: int) -> List[int]:
    result = await db.execute(
        select(SessionEntity.entity_id).where(SessionEntity.session_id == session_id)
    )
    return result.scalars().all()


async def _ensure_active_thread(db: AsyncSession, session: Session) -> MessageThread:
    """Ensure the session has an active root thread and return it."""
    if session.active_thread_id:
        thread = await db.get(MessageThread, session.active_thread_id)
        if thread:
            return thread
    thread = MessageThread(session_id=session.id)
    db.add(thread)
    await db.flush()
    session.active_thread_id = thread.id
    await db.execute(
        update(Message)
        .where(Message.session_id == session.id, Message.thread_id.is_(None))
        .values(thread_id=thread.id)
    )
    await db.flush()
    return thread


async def _get_root_thread_id(db: AsyncSession, session: Session) -> int:
    result = await db.execute(
        select(MessageThread.id)
        .where(MessageThread.session_id == session.id, MessageThread.parent_thread_id.is_(None))
        .order_by(MessageThread.created_at)
        .limit(1)
    )
    root_id = result.scalar_one_or_none()
    if root_id is None:
        root_id = (await _ensure_active_thread(db, session)).id
    return int(root_id)


async def _get_thread_path_messages(
    db: AsyncSession,
    session: Session,
    thread: MessageThread,
    roles: Optional[List[MessageRole]] = None,
    limit: Optional[int] = None,
    exclude_message_id: Optional[int] = None,
) -> List[Message]:
    messages: List[Message] = []
    chain: List[MessageThread] = []
    current = thread
    while current is not None:
        chain.append(current)
        if current.parent_thread_id:
            current = await db.get(MessageThread, current.parent_thread_id)
        else:
            current = None
    chain.reverse()
    for idx, current_thread in enumerate(chain):
        cutoff_id = None
        if idx < len(chain) - 1:
            cutoff_id = chain[idx + 1].parent_message_id
        query = select(Message).where(
            Message.thread_id == current_thread.id,
            Message.session_id == session.id,
        )
        if cutoff_id:
            query = query.where(Message.id <= cutoff_id)
        if roles:
            query = query.where(Message.role.in_(roles))
        if exclude_message_id is not None:
            query = query.where(Message.id != exclude_message_id)
        query = query.order_by(Message.created_at)
        result = await db.execute(query)
        messages.extend(result.scalars().all())

    if limit is not None and len(messages) > limit:
        messages = messages[-limit:]
    return messages


async def _fetch_recent_roleplay_history(
    db: AsyncSession, session: Session, exclude_message_id: Optional[int] = None
) -> List[dict]:
    thread = await _ensure_active_thread(db, session)
    messages = await _get_thread_path_messages(
        db,
        session,
        thread,
        roles=[MessageRole.user, MessageRole.counterparty],
        limit=ROLEPLAY_HISTORY_LIMIT,
        exclude_message_id=exclude_message_id,
    )
    history: List[dict] = []
    for msg in messages:
        role = "user" if msg.role == MessageRole.user else "assistant"
        history.append({"role": role, "content": msg.content})
    return history


def _json_default(value: object) -> str:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_dumps(payload: object) -> str:
    try:
        return orjson.dumps(payload, default=_json_default).decode("utf-8")
    except orjson.JSONEncodeError:
        return json.dumps(payload, default=_json_default)


def _sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _sse_json(event: str, payload: object) -> str:
    return _sse_event(event, _json_dumps(payload))


def _empty_grounding_pack() -> Dict[str, Any]:
    return {
        "key_points": [],
        "norms_and_expectations": [],
        "constraints_and_rules": [],
        "disputed_or_uncertain": [],
        "what_to_ask_user": [],
    }


async def _can_run_search(
    db: AsyncSession, user: User, session_id: int, trigger: Optional[str]
) -> bool:
    from ..models import Event

    max_searches = 4 if user.tier == UserTier.premium else 2
    search_count = await db.scalar(
        select(func.count()).where(
            Event.session_id == session_id,
            Event.event_type == EventType.web_grounding_called,
        )
    )
    search_count = int(search_count or 0)
    if search_count >= max_searches:
        return False
    if trigger != "user_requested" and search_count >= 1:
        return False
    return True


async def _run_grounding_pipeline(
    *,
    db: AsyncSession,
    user: User,
    session: Session,
    topic_text: str,
    template_id: str,
    enable_web_grounding: bool,
    trigger: Optional[str],
    force_user_request: bool,
    max_queries: Optional[int],
    emit_decision_before_search: bool,
    emit_shown_to_user: bool,
    add_budget_reason: bool,
    return_empty_pack_when_skipped: bool,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], int]:
    if not enable_web_grounding:
        if return_empty_pack_when_skipped:
            return _empty_grounding_pack(), [], 0
        return None, [], 0
    decision = await need_search({"topic_text": topic_text, "template_id": template_id})
    if force_user_request:
        decision["need_search"] = True
        decision.setdefault("reason_codes", []).append("USER_REQUESTED")
    if not decision.get("need_search"):
        if return_empty_pack_when_skipped:
            return _empty_grounding_pack(), [], 0
        return None, [], 0
    if emit_decision_before_search:
        await emit_event(
            db,
            EventType.web_grounding_decided,
            user.id,
            session_id=session.id,
            payload=decision,
        )
    if not await _can_run_search(db, user, session.id, trigger):
        if add_budget_reason:
            decision["need_search"] = False
            decision["reason_codes"] = decision.get("reason_codes", []) + ["BUDGET_EXCEEDED"]
        if return_empty_pack_when_skipped:
            return _empty_grounding_pack(), [], 0
        return None, [], 0
    queries = (await plan_queries({"topic_text": topic_text}, decision)).get("queries", [])
    decision_max = decision.get("max_queries")
    if isinstance(decision_max, int):
        queries = queries[:decision_max]
    if max_queries is not None:
        queries = queries[:max_queries]
    await emit_event(
        db,
        EventType.web_grounding_query_planned,
        user.id,
        session_id=session.id,
        payload={"queries": queries},
    )
    results = await run_search(queries)
    await emit_event(
        db,
        EventType.web_grounding_called,
        user.id,
        session_id=session.id,
        payload={"num_queries": len(queries)},
    )
    grounding_pack = await synthesize(results, {})
    if not emit_decision_before_search:
        await emit_event(
            db,
            EventType.web_grounding_decided,
            user.id,
            session_id=session.id,
            payload=decision,
        )
    await emit_event(
        db,
        EventType.web_grounding_pack_created,
        user.id,
        session_id=session.id,
        payload={"num_sources": len(results)},
    )
    if emit_shown_to_user:
        await emit_event(
            db,
            EventType.web_grounding_shown_to_user,
            user.id,
            session_id=session.id,
            payload={"num_sources": len(results)},
        )
    return grounding_pack, results, len(queries)


async def list_sessions(db: AsyncSession, user: User) -> List[SessionSummary]:
    """Return a list of sessions for the current user."""
    result = await db.execute(
        select(Session).where(Session.user_id == user.id).order_by(desc(Session.created_at))
    )
    return [SessionSummary.model_validate(item) for item in result.scalars().all()]


async def ensure_session_active(db: AsyncSession, user: User, session_id: int) -> None:
    """Raise if the session is missing or already ended."""
    session = await _get_session_or_404(db, session_id, user.id)
    if session.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session has ended")


async def get_session_detail(db: AsyncSession, user: User, session_id: int) -> SessionDetail:
    """Return session detail with messages and attached entities."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.attached_entities))
        .where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    thread = await _ensure_active_thread(db, session)
    root_thread_id = await _get_root_thread_id(db, session)
    path_messages = await _get_thread_path_messages(db, session, thread, roles=None)
    attached_entities = []
    if session.attached_entities:
        unique = {}
        for ent in session.attached_entities:
            unique[ent.id] = ent
        attached_entities = [EntityOut.model_validate(ent) for ent in unique.values()]
    detail = SessionDetail(
        id=session.id,
        template_id=session.template_id,
        title=session.title,
        topic_text=session.topic_text,
        counterparty_style=session.counterparty_style,
        created_at=session.created_at,
        ended_at=session.ended_at,
        active_thread_id=session.active_thread_id,
        root_thread_id=root_thread_id,
        attached_entities=attached_entities,
        messages=[SessionMessageOut.model_validate(msg) for msg in path_messages],
    )
    return detail


async def update_session(
    db: AsyncSession, user: User, session_id: int, req: SessionUpdateRequest
) -> SessionDetail:
    """Update session metadata such as title or counterparty style."""
    session = await _get_session_or_404(db, session_id, user.id)
    if req.title is not None:
        session.title = req.title
    if req.counterparty_style is not None:
        session.counterparty_style = req.counterparty_style
    await db.flush()
    return await get_session_detail(db, user, session_id)


async def attach_entities(db: AsyncSession, user: User, session_id: int, entity_ids: List[int]) -> None:
    """Attach entities to a session."""
    session = await _get_session_or_404(db, session_id, user.id)
    entities = []
    for entity_id in entity_ids:
        entity = await db.get(Entity, entity_id)
        if entity and getattr(entity, "user_id", None) == user.id:
            entities.append(entity)
    await attach_entities_to_session(db, session, entities)
    await emit_event(
        db,
        EventType.entity_attached,
        user.id,
        session_id=session.id,
        payload={"entity_ids": entity_ids},
    )


async def detach_entities(db: AsyncSession, user: User, session_id: int, entity_ids: List[int]) -> None:
    """Detach entities from a session."""
    session = await _get_session_or_404(db, session_id, user.id)
    if not entity_ids:
        return
    await db.execute(
        delete(SessionEntity).where(
            SessionEntity.session_id == session.id,
            SessionEntity.entity_id.in_(entity_ids),
        )
    )
    await db.flush()
    await emit_event(
        db,
        EventType.entity_detached,
        user.id,
        session_id=session.id,
        payload={"entity_ids": entity_ids},
    )


async def stream_message(
    db: AsyncSession,
    user: User,
    session_id: int,
    req: PostMessageRequest,
) -> AsyncIterator[str]:
    """Stream a roleplay response as SSE events."""
    try:
        session = await _get_session_or_404(db, session_id, user.id)
        if session.ended_at is not None:
            yield _sse_json("error", {"detail": "Session has ended"})
            return
        active_thread = await _ensure_active_thread(db, session)
        case_snapshot = await get_or_create_case_snapshot(db, session, None)
        role = MessageRole.user if req.channel == "roleplay" else MessageRole.coach
        user_message = Message(
            session_id=session.id,
            thread_id=active_thread.id,
            role=role,
            content=req.content,
        )
        db.add(user_message)
        await db.flush()
        history: List[dict] = []
        if req.channel == "roleplay":
            history = await _fetch_recent_roleplay_history(
                db, session, exclude_message_id=user_message.id
            )
        await emit_event(
            db,
            EventType.message_user_sent if role == MessageRole.user else EventType.message_coach_sent,
            user.id,
            session_id=session.id,
            payload={"content": req.content},
        )
        intake_submitted = req.content.strip().startswith("Intake summary:")
        if intake_submitted:
            case_snapshot = await update_case_snapshot_from_intake(
                db,
                session,
                questions=[],
                answers={},
                summary=req.content,
            )
        else:
            case_snapshot = await update_case_snapshot_from_message(
                db,
                session,
                case_snapshot,
                req.content,
                role="user",
            )
        entity_ids = await _fetch_attached_entity_ids(db, session.id)
        candidate_facts = await extract_candidate_facts(req.content, entity_ids)
        extracted_fact_models = []
        for cand in candidate_facts:
            fact = Fact(
                user_id=user.id,
                session_id=session.id,
                subject_entity_id=cand.get("subject_entity_id"),
                key=cand.get("key"),
                value=cand.get("value"),
                scope=KnowledgeScope.session_scope,
                confidence=1.0,
                source_type="model_extracted",
                source_ref=f"message:{user_message.id}",
            )
            db.add(fact)
            await db.flush()
            extracted_fact_models.append(fact)
        grounding_topic = " ".join(
            part for part in [session.topic_text or "", req.content or ""] if part
        )
        grounding_pack, _grounding_sources, _grounding_budget = await _run_grounding_pipeline(
            db=db,
            user=user,
            session=session,
            topic_text=grounding_topic,
            template_id=session.template_id,
            enable_web_grounding=bool(req.enable_web_grounding),
            trigger=req.web_grounding_trigger,
            force_user_request=False,
            max_queries=None,
            emit_decision_before_search=False,
            emit_shown_to_user=False,
            add_budget_reason=True,
            return_empty_pack_when_skipped=False,
        )
        visible_facts = await compute_visible_facts(db, session)
        strategy_selection = await get_latest_strategy_selection(db, session.id)
        if intake_submitted and strategy_selection is None:
            try:
                strategy_selection = await run_strategy_selection(
                    db, session, case_snapshot.payload, user_intent=req.content
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Strategy selection failed: %s", exc)
        strategy_context = None
        if strategy_selection:
            try:
                strategy_context = get_strategy(strategy_selection.selected_strategy_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Strategy context load failed: %s", exc)
        counterparty_profile = case_snapshot.payload.get("parties", {}).get("counterpart", {})
        counterparty_stance = counterparty_profile.get("stance")
        counterparty_constraints = counterparty_profile.get("constraints") or []
        await emit_event(
            db,
            EventType.disclosure_in_chat,
            user.id,
            session_id=session.id,
            payload={
                "template_id": session.template_id,
                "counterparty_style": session.counterparty_style,
                "entity_ids": entity_ids,
                "visible_facts": [
                    {"id": fact.get("id"), "key": fact.get("key"), "value": fact.get("value")}
                    for fact in visible_facts
                ],
                "grounding_used": bool(grounding_pack),
            },
        )
        counterparty_chunks: List[str] = []
        coach_panel = None
        if req.channel == "roleplay":
            orchestration = await run_orchestration(
                req.content,
                visible_facts,
                grounding_pack,
                session.counterparty_style,
                history,
                session.topic_text,
                session.template_id,
                strategy_context,
                counterparty_stance,
                counterparty_constraints,
                include_coach=user.tier == UserTier.premium,
                stream_roleplay=True,
            )
            prompt_messages = orchestration.get("prompt_messages") or []
            coach_panel = orchestration.get("coach_panel")
            await emit_event(
                db,
                EventType.orchestration_context_built,
                user.id,
                session_id=session.id,
                payload={
                    "messages": prompt_messages,
                    "template_id": session.template_id,
                    "topic_text": session.topic_text,
                    "history_count": len(history),
                    "history_limit": ROLEPLAY_HISTORY_LIMIT,
                    "strategy_id": strategy_context.get("strategy_id") if strategy_context else None,
                },
            )
            await emit_event(
                db,
                EventType.message_stream_started,
                user.id,
                session_id=session.id,
                payload={"channel": req.channel},
            )
            async for token in generate_roleplay_stream(
                req.content,
                visible_facts,
                grounding_pack,
                session.counterparty_style,
                history,
                prompt_messages=prompt_messages,
                strategy_context=strategy_context,
                counterparty_stance=counterparty_stance,
                counterparty_constraints=counterparty_constraints,
            ):
                if token:
                    counterparty_chunks.append(token)
                    yield _sse_json("token", token)
            counterparty_message = "".join(counterparty_chunks).strip()
            reply = Message(
                session_id=session.id,
                thread_id=active_thread.id,
                role=MessageRole.counterparty,
                content=counterparty_message,
            )
            db.add(reply)
            await emit_event(
                db,
                EventType.message_counterparty_sent,
                user.id,
                session_id=session.id,
                payload={"content": counterparty_message},
            )
            case_snapshot = await update_case_snapshot_from_message(
                db,
                session,
                case_snapshot,
                counterparty_message,
                role="counterparty",
            )
            await emit_event(
                db,
                EventType.message_stream_ended,
                user.id,
                session_id=session.id,
                payload={"content_length": len(counterparty_message)},
            )
        else:
            counterparty_message = None
        extracted_facts = [
            {
                "id": f.id,
                "subject_entity_id": f.subject_entity_id,
                "key": f.key,
                "value": f.value,
                "scope": f.scope.value if hasattr(f.scope, "value") else f.scope,
                "source_ref": f.source_ref,
            }
            for f in extracted_fact_models
        ]
        strategy_selection_payload = None
        if strategy_selection:
            strategy_selection_payload = dict(strategy_selection.selection_payload)
            strategy_selection_payload["selected_strategy_id"] = strategy_selection.selected_strategy_id
        payload = {
            "counterparty_message": counterparty_message,
            "coach_panel": coach_panel,
            "grounding_pack": grounding_pack,
            "extracted_facts": extracted_facts,
            "strategy_selection": strategy_selection_payload,
        }
        yield _sse_json("done", payload)
    except HTTPException as exc:
        await db.rollback()
        yield _sse_json("error", {"detail": exc.detail})
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        yield _sse_json("error", {"detail": str(exc)})


async def end_session(db: AsyncSession, user: User, session_id: int) -> EndSessionResponse:
    """Mark a session as ended and provide a recap."""
    session = await _get_session_or_404(db, session_id, user.id)
    if session.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session already ended")
    session.ended_at = datetime.utcnow()
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    payload = {
        "topic_text": session.topic_text,
        "template_id": session.template_id,
        "messages": [
            {"role": msg.role.value if hasattr(msg.role, "value") else str(msg.role), "content": msg.content}
            for msg in messages
        ],
        "premium": user.tier == UserTier.premium,
    }
    system_prompt = (
        "You are the Session Recap agent. Produce a concise descriptive recap of the session. "
        "If premium=true, also produce an after_action_report with coaching insights. "
        "If premium=false, do not include advice or coaching language. "
        'Output JSON only: {"recap":"...","after_action_report":"..."}'
    )
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot generate session recap.")
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.2,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=SessionRecapResult, **completion_kwargs)
        recap_result = response
    except Exception:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty session recap.")
        recap_result = SessionRecapResult.model_validate_json(content)
    recap = recap_result.recap
    after_action_report = recap_result.after_action_report if user.tier == UserTier.premium else None
    await emit_event(db, EventType.session_ended, user.id, session_id=session.id, payload={})
    return EndSessionResponse(recap=recap, after_action_report=after_action_report)


async def commit_memory_review(
    db: AsyncSession,
    user: User,
    session_id: int,
    req: MemoryReviewRequest,
) -> MemoryReviewResponse:
    """Commit facts according to user memory review decisions."""
    session = await _get_session_or_404(db, session_id, user.id)
    committed = await commit_facts(
        db, session, [d.model_dump() for d in req.decisions], user_id=user.id
    )
    # Build response
    updated_facts = [
        {
            "id": f.id,
            "subject_entity_id": f.subject_entity_id,
            "key": f.key,
            "value": f.value,
            "scope": f.scope,
        }
        for f in committed
    ]
    # Emit events per fact
    for f in committed:
        await emit_event(
            db,
            EventType.fact_confirmed if f.scope == KnowledgeScope.global_scope else EventType.fact_suggested,
            user.id,
            session_id=session.id,
            payload={"fact_id": f.id, "scope": f.scope.value},
        )
    return MemoryReviewResponse(updated_facts=updated_facts)


async def list_session_facts(db: AsyncSession, user: User, session_id: int) -> List[Fact]:
    """Return session-only facts for memory review."""
    await _get_session_or_404(db, session_id, user.id)
    result = await db.execute(
        select(Fact).where(
            Fact.user_id == user.id,
            Fact.session_id == session_id,
            Fact.scope == KnowledgeScope.session_scope,
        )
    )
    return result.scalars().all()


async def list_session_events(db: AsyncSession, user: User, session_id: int) -> List:
    """Return ordered events for a session."""
    await _get_session_or_404(db, session_id, user.id)
    from ..models import Event

    result = await db.execute(
        select(Event).where(Event.session_id == session_id).order_by(Event.created_at)
    )
    return result.scalars().all()


async def list_route_branches(
    db: AsyncSession,
    user: User,
    session_id: int,
    parent_message_id: Optional[int] = None,
) -> List[dict]:
    """List stored route branches for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    await _ensure_active_thread(db, session)
    query = select(MessageThread).where(
        MessageThread.session_id == session.id, MessageThread.parent_message_id.is_not(None)
    )
    if parent_message_id is not None:
        query = query.where(MessageThread.parent_message_id == parent_message_id)
    result = await db.execute(query.order_by(MessageThread.created_at))
    threads = result.scalars().all()
    if not threads:
        return []
    thread_ids = [thread.id for thread in threads]
    message_result = await db.execute(
        select(Message)
        .where(
            Message.thread_id.in_(thread_ids),
            Message.role == MessageRole.counterparty,
        )
        .order_by(Message.created_at)
    )
    messages = message_result.scalars().all()
    first_message_by_thread: Dict[int, Message] = {}
    for msg in messages:
        if msg.thread_id not in first_message_by_thread:
            first_message_by_thread[msg.thread_id] = msg
    branches: List[dict] = []
    for thread in threads:
        counterparty_message = first_message_by_thread.get(thread.id)
        branches.append(
            {
                "branch_id": str(thread.id),
                "thread_id": thread.id,
                "parent_message_id": int(thread.parent_message_id),
                "variant": thread.variant or "LIKELY",
                "counterparty_response": counterparty_message.content if counterparty_message else "",
                "rationale": thread.rationale or "",
                "action_label": thread.action_label or "",
                "branch_label": thread.branch_label or "",
                "created_at": thread.created_at.isoformat(),
                "is_active": thread.id == session.active_thread_id,
            }
        )
    return branches


async def activate_thread(
    db: AsyncSession, user: User, session_id: int, thread_id: int
) -> SessionDetail:
    """Activate a thread (branch) as the current mainline path."""
    session = await _get_session_or_404(db, session_id, user.id)
    thread = await db.get(MessageThread, thread_id)
    if thread is None or thread.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    session.active_thread_id = thread.id
    await db.flush()
    return await get_session_detail(db, user, session_id)


async def update_branch(
    db: AsyncSession,
    user: User,
    session_id: int,
    thread_id: int,
    branch_label: Optional[str] = None,
    counterparty_response: Optional[str] = None,
) -> dict:
    """Update a branch label or its counterparty response."""
    session = await _get_session_or_404(db, session_id, user.id)
    thread = await db.get(MessageThread, thread_id)
    if thread is None or thread.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    if thread.parent_message_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit mainline thread.")
    if branch_label is not None:
        thread.branch_label = branch_label.strip() or None
    if counterparty_response is not None:
        msg_result = await db.execute(
            select(Message)
            .where(
                Message.thread_id == thread.id,
                Message.role == MessageRole.counterparty,
            )
            .order_by(Message.created_at)
            .limit(1)
        )
        msg = msg_result.scalar_one_or_none()
        if msg is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch response not found.")
        msg.content = counterparty_response.strip()
    await db.flush()
    branch_list = await list_route_branches(db, user, session_id, parent_message_id=thread.parent_message_id)
    for branch in branch_list:
        if str(branch.get("thread_id")) == str(thread.id):
            return branch
    return {
        "branch_id": str(thread.id),
        "thread_id": thread.id,
        "parent_message_id": int(thread.parent_message_id),
        "variant": thread.variant or "LIKELY",
        "counterparty_response": counterparty_response or "",
        "rationale": thread.rationale or "",
        "action_label": thread.action_label or "",
        "branch_label": thread.branch_label or "",
        "created_at": thread.created_at.isoformat(),
        "is_active": thread.id == session.active_thread_id,
    }


async def copy_branch(
    db: AsyncSession,
    user: User,
    session_id: int,
    thread_id: int,
    branch_label: Optional[str] = None,
    counterparty_response: Optional[str] = None,
) -> dict:
    """Copy a branch into a new branch thread."""
    session = await _get_session_or_404(db, session_id, user.id)
    source = await db.get(MessageThread, thread_id)
    if source is None or source.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    if source.parent_message_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot copy mainline thread.")
    msg_result = await db.execute(
        select(Message)
        .where(Message.thread_id == source.id, Message.role == MessageRole.counterparty)
        .order_by(Message.created_at)
        .limit(1)
    )
    msg = msg_result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch response not found.")
    new_thread = MessageThread(
        session_id=session.id,
        parent_thread_id=source.parent_thread_id,
        parent_message_id=source.parent_message_id,
        variant=source.variant,
        rationale=source.rationale,
        action_label=source.action_label,
        branch_label=branch_label or source.branch_label or source.action_label,
    )
    db.add(new_thread)
    await db.flush()
    new_msg = Message(
        session_id=session.id,
        thread_id=new_thread.id,
        role=MessageRole.counterparty,
        content=(counterparty_response or msg.content).strip(),
    )
    db.add(new_msg)
    await db.flush()
    return {
        "branch_id": str(new_thread.id),
        "thread_id": new_thread.id,
        "parent_message_id": int(new_thread.parent_message_id),
        "variant": new_thread.variant or "LIKELY",
        "counterparty_response": new_msg.content,
        "rationale": new_thread.rationale or "",
        "action_label": new_thread.action_label or "",
        "branch_label": new_thread.branch_label or "",
        "created_at": new_thread.created_at.isoformat(),
        "is_active": new_thread.id == session.active_thread_id,
    }


async def delete_branch(
    db: AsyncSession, user: User, session_id: int, thread_id: int
) -> None:
    """Delete a branch thread and its messages."""
    session = await _get_session_or_404(db, session_id, user.id)
    thread = await db.get(MessageThread, thread_id)
    if thread is None or thread.session_id != session.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    if thread.parent_message_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete mainline thread.")
    if session.active_thread_id == thread.id:
        root_id = await _get_root_thread_id(db, session)
        session.active_thread_id = root_id
    await db.delete(thread)
    await db.flush()


async def generate_route(
    db: AsyncSession,
    user: User,
    session_id: int,
    variant: str,
    existing_routes: Optional[List[dict]] = None,
    parent_message_id: Optional[int] = None,
) -> dict:
    """Generate a new route branch anchored to the latest user message."""
    session = await _get_session_or_404(db, session_id, user.id)
    snapshot = await get_or_create_case_snapshot(db, session, None)
    active_thread = await _ensure_active_thread(db, session)
    # parent_message_id = latest user message (unless explicitly provided)
    path_messages = await _get_thread_path_messages(
        db,
        session,
        active_thread,
        roles=[MessageRole.user, MessageRole.counterparty],
        limit=None,
    )
    if parent_message_id is None:
        for msg in reversed(path_messages):
            if msg.role == MessageRole.user:
                parent_message_id = msg.id
                break
    if not parent_message_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user message found to anchor the route.",
        )
    parent_message = None
    for msg in path_messages:
        if msg.id == parent_message_id:
            parent_message = msg
            break
    if parent_message is None or parent_message.role != MessageRole.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid parent message for route generation.",
        )
    parent_thread_id = parent_message.thread_id
    if not parent_thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent message is missing a thread assignment.",
        )
    history_messages: List[Message] = []
    for msg in path_messages:
        history_messages.append(msg)
        if msg.id == parent_message_id:
            break
    history = [
        {"role": "user" if msg.role == MessageRole.user else "assistant", "content": msg.content}
        for msg in history_messages
        if msg.role in [MessageRole.user, MessageRole.counterparty]
    ]
    strategy_selection = await get_latest_strategy_selection(db, session.id)
    strategy_context = None
    if strategy_selection:
        try:
            strategy_context = get_strategy(strategy_selection.selected_strategy_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Strategy context load failed: %s", exc)
    result = await generate_route_branch(
        case_snapshot=snapshot.payload,
        history=history,
        strategy_context=strategy_context,
        counterparty_style=session.counterparty_style,
        variant=variant,
        existing_routes=existing_routes or [],
    )
    branch_thread = MessageThread(
        session_id=session.id,
        parent_thread_id=parent_thread_id,
        parent_message_id=int(parent_message_id),
        variant=variant,
        rationale=result.rationale,
        action_label=result.action_label,
        branch_label=result.action_label,
    )
    db.add(branch_thread)
    await db.flush()
    branch_message = Message(
        session_id=session.id,
        thread_id=branch_thread.id,
        role=MessageRole.counterparty,
        content=result.counterparty_response,
    )
    db.add(branch_message)
    await db.flush()
    branch = {
        "branch_id": str(branch_thread.id),
        "thread_id": branch_thread.id,
        "parent_message_id": int(parent_message_id),
        "variant": variant,
        "counterparty_response": result.counterparty_response,
        "rationale": result.rationale,
        "action_label": result.action_label,
        "branch_label": result.action_label,
        "created_at": branch_thread.created_at.isoformat(),
    }
    return branch


async def get_case_snapshot_detail(
    db: AsyncSession, user: User, session_id: int
) -> CaseSnapshot:
    """Return the current case snapshot for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    snapshot = await get_case_snapshot(db, session.id)
    if snapshot is None:
        snapshot = await get_or_create_case_snapshot(db, session, None)
    return snapshot


async def update_case_snapshot(
    db: AsyncSession, user: User, session_id: int, patches: List[dict]
) -> CaseSnapshot:
    """Apply JSON patch updates to the case snapshot."""
    session = await _get_session_or_404(db, session_id, user.id)
    snapshot = await get_or_create_case_snapshot(db, session, None)
    updated_payload = apply_case_patches(snapshot.payload, patches)
    updated_payload["updated_at"] = datetime.utcnow().isoformat()
    try:
        validate_case_snapshot(updated_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Case snapshot validation failed (patch). Error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid case snapshot update.") from exc
    snapshot.payload = updated_payload
    await db.flush()
    return snapshot


async def submit_intake(
    db: AsyncSession,
    user: User,
    session_id: int,
    questions: List[str],
    answers: Dict[str, str],
    summary: Optional[str],
) -> tuple[CaseSnapshot, Optional[StrategySelection]]:
    """Update the case snapshot using intake answers and run strategy selection."""
    session = await _get_session_or_404(db, session_id, user.id)
    snapshot = await update_case_snapshot_from_intake(db, session, questions, answers, summary)
    existing = await get_latest_strategy_selection(db, session.id)
    if existing is not None:
        return snapshot, existing
    selection = None
    try:
        selection = await run_strategy_selection(db, session, snapshot.payload, user_intent=summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Strategy selection failed after intake: %s", exc)
    return snapshot, selection


async def get_strategy_selection(
    db: AsyncSession, user: User, session_id: int
) -> Optional[StrategySelection]:
    """Return the latest strategy selection for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    return await get_latest_strategy_selection(db, session.id)


async def get_latest_strategy_execution(
    db: AsyncSession, user: User, session_id: int
) -> Optional[StrategyExecution]:
    """Return the latest strategy execution for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    return await fetch_latest_strategy_execution(db, session.id)


async def run_strategy_selection_for_session(
    db: AsyncSession,
    user: User,
    session_id: int,
    user_intent: Optional[str] = None,
) -> StrategySelection:
    """Run strategy selection if none exists yet for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    existing = await get_latest_strategy_selection(db, session.id)
    if existing is not None:
        return existing
    snapshot = await get_or_create_case_snapshot(db, session, None)
    return await run_strategy_selection(db, session, snapshot.payload, user_intent=user_intent)


async def execute_strategy(
    db: AsyncSession,
    user: User,
    session_id: int,
    strategy_id: Optional[str],
    inputs: Dict[str, Any],
) -> StrategyExecution:
    """Execute a strategy for the session and persist artifacts."""
    session = await _get_session_or_404(db, session_id, user.id)
    snapshot = await get_or_create_case_snapshot(db, session, None)
    selection = await get_latest_strategy_selection(db, session.id)
    chosen_strategy_id = strategy_id or (selection.selected_strategy_id if selection else None)
    if not chosen_strategy_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No strategy selected for this session.",
        )
    try:
        execution = await execute_strategy_for_session(
            db,
            session,
            snapshot.payload,
            chosen_strategy_id,
            inputs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if execution.case_patches:
        updated_payload = apply_case_patches(snapshot.payload, execution.case_patches)
        updated_payload["updated_at"] = datetime.utcnow().isoformat()
        try:
            validate_case_snapshot(updated_payload)
            snapshot.payload = updated_payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("Case snapshot validation failed after strategy execution: %s", exc)
    await db.flush()
    return execution


async def explicit_grounding(
    db: AsyncSession,
    user: User,
    session_id: int,
    req: GroundingRequest,
) -> tuple[dict, List[dict], int]:
    """Run explicit grounding for the session."""
    session = await _get_session_or_404(db, session_id, user.id)
    topic = req.user_question or session.topic_text or ""
    grounding_pack, sources, budget = await _run_grounding_pipeline(
        db=db,
        user=user,
        session=session,
        topic_text=topic,
        template_id=session.template_id,
        enable_web_grounding=True,
        trigger="user_requested",
        force_user_request=req.mode == "user_requested",
        max_queries=req.max_queries,
        emit_decision_before_search=True,
        emit_shown_to_user=True,
        add_budget_reason=False,
        return_empty_pack_when_skipped=True,
    )
    return grounding_pack, sources, budget
