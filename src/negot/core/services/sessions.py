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
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import orjson
from pydantic import BaseModel, Field

from fastapi import HTTPException, status
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..events import emit_event
from ..models import (
    Entity,
    EventType,
    Message,
    MessageRole,
    Session,
    SessionEntity,
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
    SessionSummary,
    SessionUpdateRequest,
)
from .kg import attach_entities_to_session, commit_facts, compute_visible_facts, list_entities
from .orchestrator import (
    extract_candidate_facts,
    generate_roleplay_stream,
    run_orchestration,
)
from .question_planner import generate_intake_questions
from .entity_proposer import propose_entities
from .templates import create_template_proposal_for_other, select_template
from .web_grounding import need_search, plan_queries, run_search, synthesize
from .llm_utils import acompletion_with_retry, extract_completion_text

ROLEPLAY_HISTORY_LIMIT = 12


class SessionRecapResult(BaseModel):
    recap: str = Field(..., description="Descriptive recap of the session.")
    after_action_report: Optional[str] = Field(None, description="Premium coaching summary.")


async def create_session(
    db: AsyncSession,
    user: User,
    req: CreateSessionRequest,
) -> CreateSessionResponse:
    """Create a new negotiation session for a user."""
    template_id = await select_template(req.topic_text)
    title = (req.topic_text or "Negotiation Session").strip()[:80]
    session = Session(
        user_id=user.id,
        template_id=template_id,
        title=title or "Negotiation Session",
        topic_text=req.topic_text,
        counterparty_style=req.counterparty_style,
    )
    db.add(session)
    await db.flush()
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
    # Build minimal intake questions based on template
    attached_entities_state = [
        {"id": entity.id, "name": entity.name, "type": entity.type}
        for entity in attached_entities
    ]
    intake_questions = await generate_intake_questions(
        topic_text=req.topic_text,
        template_id=template_id,
        counterparty_style=req.counterparty_style,
        attached_entities=attached_entities_state,
        history=[],
    )
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


async def _fetch_recent_roleplay_history(
    db: AsyncSession, session_id: int, exclude_message_id: Optional[int] = None
) -> List[dict]:
    query = (
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role.in_([MessageRole.user, MessageRole.counterparty]),
        )
        .order_by(desc(Message.created_at))
        .limit(ROLEPLAY_HISTORY_LIMIT)
    )
    if exclude_message_id is not None:
        query = query.where(Message.id != exclude_message_id)
    result = await db.execute(query)
    messages = list(result.scalars().all())
    messages.reverse()
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
        .options(selectinload(Session.messages), selectinload(Session.attached_entities))
        .where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    detail = SessionDetail.model_validate(session)
    if detail.attached_entities:
        unique = {}
        for ent in detail.attached_entities:
            unique[ent.id] = ent
        detail.attached_entities = list(unique.values())
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
    return SessionDetail.model_validate(session)


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
        role = MessageRole.user if req.channel == "roleplay" else MessageRole.coach
        user_message = Message(
            session_id=session.id,
            role=role,
            content=req.content,
        )
        db.add(user_message)
        await db.flush()
        history: List[dict] = []
        if req.channel == "roleplay":
            history = await _fetch_recent_roleplay_history(
                db, session.id, exclude_message_id=user_message.id
            )
        await emit_event(
            db,
            EventType.message_user_sent if role == MessageRole.user else EventType.message_coach_sent,
            user.id,
            session_id=session.id,
            payload={"content": req.content},
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
            ):
                if token:
                    counterparty_chunks.append(token)
                    yield _sse_json("token", token)
            counterparty_message = "".join(counterparty_chunks).strip()
            reply = Message(
                session_id=session.id,
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
        payload = {
            "counterparty_message": counterparty_message,
            "coach_panel": coach_panel,
            "grounding_pack": grounding_pack,
            "extracted_facts": extracted_facts,
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
