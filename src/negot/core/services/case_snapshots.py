"""
Case snapshot creation and update utilities.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import jsonpatch
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import CaseSnapshot, Session
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object
from .strategy_packs import validate_case_snapshot

logger = logging.getLogger(__name__)

CASE_PATCH_SYSTEM_PROMPT = """You are the Case Snapshot Update agent.
Update the CaseSnapshot using ONLY the provided evidence. Do not invent values.
Return JSON only in this format: {"patches":[{...}]}.

Rules:
- Use RFC6902 JSON Patch operations.
- Only patch fields that are supported by the CaseSnapshot schema.
- Do not modify case_id.
- If evidence does not change the snapshot, return an empty patches list.
"""


class CasePatchResult(BaseModel):
    patches: List[dict] = Field(default_factory=list)


TEMPLATE_DOMAIN_MAP = {
    "rent_renewal": "RENT_HOUSING",
    "salary_offer": "JOB_OFFER_COMP",
    "refund_complaint": "PROCUREMENT_VENDOR",
    "workplace_boundary": "GENERAL",
    "roommate_conflict": "PERSONAL_FAMILY",
    "relationship_disagreement": "PERSONAL_FAMILY",
    "dating_expectations": "PERSONAL_FAMILY",
    "friendship_conflict": "PERSONAL_FAMILY",
    "money_with_friends": "PERSONAL_FAMILY",
    "family_parental_disagreement": "PERSONAL_FAMILY",
    "other": "GENERAL",
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _case_id(session_id: int) -> str:
    return f"CASE_{session_id}"


def _default_issue(topic_text: str) -> dict:
    name = (topic_text or "Primary issue").strip()[:120] or "Primary issue"
    return {
        "issue_id": "ISSUE_PRIMARY",
        "name": name,
        "type": "TEXT",
        "priority": 5,
        "my_position": None,
        "their_position": None,
        "my_interest": None,
        "their_interest": None,
    }


def build_initial_case_snapshot(session: Session, channel: Optional[str]) -> dict:
    domain = TEMPLATE_DOMAIN_MAP.get(session.template_id, "GENERAL")
    channel_value = (channel or "DM").upper()
    return {
        "case_id": _case_id(session.id),
        "updated_at": _now_iso(),
        "domain": domain,
        "channel": channel_value,
        "stage": "INTAKE",
        "parties": {
            "me": {"name": "User", "role": "user", "preferences": {}},
            "counterpart": {
                "name": "Counterparty",
                "role": "counterparty",
                "persona_hints": [],
                "stance": None,
                "constraints": [],
            },
            "stakeholders": [],
        },
        "issues": [_default_issue(session.topic_text or "")],
        "objectives": {"target": None, "acceptable": None, "walk_away": None, "notes": ""},
        "constraints": [],
        "risk_profile": {"relationship_risk": "MEDIUM", "time_pressure": "MEDIUM", "risk_tolerance": "MEDIUM"},
        "timeline": {"recent_events": []},
        "offer_matrix": {"packages": []},
        "concession_ledger": [],
        "route_branches": [],
        "intake": {"questions": [], "answers": {}, "summary": None},
    }


def append_timeline_event(payload: dict, event_type: str, summary: str, raw_text: Optional[str]) -> dict:
    timeline = payload.get("timeline") or {}
    recent = timeline.get("recent_events") or []
    event_id = f"EVENT_{len(recent) + 1}"
    event = {
        "event_id": event_id,
        "ts": _now_iso(),
        "type": event_type,
        "summary": summary.strip()[:200] if summary else "Message",
    }
    if raw_text:
        event["raw_text"] = raw_text
    recent.append(event)
    timeline["recent_events"] = recent
    payload["timeline"] = timeline
    return payload


def apply_case_patches(payload: dict, patches: List[dict]) -> dict:
    if not patches:
        return payload
    try:
        patch = jsonpatch.JsonPatch(patches)
        return patch.apply(payload, in_place=False)
    except (jsonpatch.JsonPatchException, jsonpatch.JsonPointerException) as exc:
        logger.warning("Failed to apply case patches: %s", exc)
        return payload


async def _extract_case_patches(payload: dict, evidence: dict) -> List[dict]:
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot update case snapshot.")
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": CASE_PATCH_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"case_snapshot": payload, "evidence": evidence}, default=str)},
        ],
        "temperature": 0.2,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    response = await acompletion_with_retry(**completion_kwargs)
    content = extract_completion_text(response)
    if not content:
        return []
    try:
        parsed = CasePatchResult.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse case patch output. Error: %s", exc)
        extracted = extract_json_object(content)
        if extracted is None:
            return []
        parsed = CasePatchResult.model_validate(extracted)
    return parsed.patches


async def get_case_snapshot(db: AsyncSession, session_id: int) -> Optional[CaseSnapshot]:
    result = await db.execute(select(CaseSnapshot).where(CaseSnapshot.session_id == session_id))
    return result.scalar_one_or_none()


async def get_or_create_case_snapshot(
    db: AsyncSession, session: Session, channel: Optional[str]
) -> CaseSnapshot:
    existing = await get_case_snapshot(db, session.id)
    if existing:
        return existing
    payload = build_initial_case_snapshot(session, channel)
    snapshot = CaseSnapshot(session_id=session.id, payload=payload)
    db.add(snapshot)
    await db.flush()
    return snapshot


async def update_case_snapshot_from_intake(
    db: AsyncSession,
    session: Session,
    questions: List[str],
    answers: Dict[str, str],
    summary: Optional[str] = None,
) -> CaseSnapshot:
    snapshot = await get_or_create_case_snapshot(db, session, channel=None)
    evidence = {
        "type": "intake",
        "topic_text": session.topic_text,
        "template_id": session.template_id,
        "questions": questions,
        "answers": answers,
        "summary": summary,
    }
    patches = await _extract_case_patches(snapshot.payload, evidence)
    updated_payload = apply_case_patches(snapshot.payload, patches)
    updated_payload["intake"] = {
        "questions": questions,
        "answers": answers,
        "summary": summary,
    }
    updated_payload["updated_at"] = _now_iso()
    try:
        validate_case_snapshot(updated_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Case snapshot validation failed (intake). Error: %s", exc)
        fallback_payload = dict(snapshot.payload)
        fallback_payload["intake"] = {
            "questions": questions,
            "answers": answers,
            "summary": summary,
        }
        fallback_payload["updated_at"] = _now_iso()
        updated_payload = fallback_payload
    snapshot.payload = updated_payload
    await db.flush()
    return snapshot


async def update_case_snapshot_from_message(
    db: AsyncSession,
    session: Session,
    snapshot: CaseSnapshot,
    message_text: str,
    role: str,
) -> CaseSnapshot:
    evidence = {
        "type": "message",
        "role": role,
        "text": message_text,
        "template_id": session.template_id,
    }
    patches = await _extract_case_patches(snapshot.payload, evidence)
    updated_payload = apply_case_patches(snapshot.payload, patches)
    event_type = "MESSAGE_OUT" if role == "user" else "MESSAGE_IN"
    updated_payload = append_timeline_event(
        updated_payload, event_type, summary=message_text, raw_text=message_text
    )
    if updated_payload.get("stage") == "INTAKE":
        updated_payload["stage"] = "BARGAINING"
    updated_payload["updated_at"] = _now_iso()
    try:
        validate_case_snapshot(updated_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Case snapshot validation failed (message). Error: %s", exc)
        updated_payload = snapshot.payload
    snapshot.payload = updated_payload
    await db.flush()
    return snapshot
