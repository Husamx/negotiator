"""
Integration tests for the session endpoints.

These tests spin up the FastAPI application using the in‑memory SQLite
database and verify that sessions can be created, messages can be
exchanged and memory review operates as expected. The tests use
pytest‑asyncio to run asynchronous test functions.
"""
import asyncio
import json
import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from negot.api.main import create_app
from negot.core.config import get_settings
from negot.core.db import init_db_schema, get_db_session


@pytest.fixture(autouse=True)
def set_test_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the DATABASE_URL to use an in-memory SQLite DB for tests."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("NEGOT_ENV", "test")
    monkeypatch.setenv("LITELLM_MODEL", "test-model")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    # Recreate settings cache so new env takes effect
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_acompletion_with_retry(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("stream"):
            async def _stream():
                yield {"choices": [{"delta": {"content": "Hello"}}]}
                yield {"choices": [{"delta": {"content": " there"}}]}
            return _stream()
        messages = kwargs.get("messages") or []
        system = messages[0]["content"] if messages else ""
        if "Intake Question Agent" in system:
            content = json.dumps({"questions": ["Who are you negotiating with?"]})
        elif "Template Router agent" in system:
            content = json.dumps({"template_id": "salary_offer", "confidence": 0.9, "rationale": "Matches salary topic."})
        elif "Web Grounding NeedSearch agent" in system:
            content = json.dumps(
                {
                    "need_search": False,
                    "reason_codes": [],
                    "max_queries": 0,
                    "max_sources_per_query": 0,
                    "search_depth": "basic",
                    "topic": "general",
                }
            )
        elif "Web Grounding QueryPlanner agent" in system:
            content = json.dumps({"queries": [], "must_have_evidence": [], "stop_conditions": []})
        elif "Web Grounding EvidenceSynthesizer agent" in system:
            content = json.dumps(
                {
                    "key_points": [],
                    "norms_and_expectations": [],
                    "constraints_and_rules": [],
                    "disputed_or_uncertain": [],
                    "what_to_ask_user": [],
                }
            )
        elif "Entity Proposer agent" in system:
            content = json.dumps({"entity_ids": [], "rationale": "No existing entities."})
        elif "Visibility Agent" in system:
            content = json.dumps({"visible_fact_ids": [], "rationale": "No visible facts yet."})
        elif "Premium Coaching agent" in system:
            content = json.dumps(
                {
                    "suggestions": [{"reply": "A", "text": "Ask a clarifying question.", "intent": "clarify"}],
                    "strategy": {"anchoring": "Start high.", "concessions": "Small steps.", "questions": "Learn goals.", "red_lines": "Know limits."},
                    "critique": "Clear message.",
                    "scenario_branches": [{"label": "Agree", "next_step": "Confirm details."}],
                    "after_action_report": "Reflect on outcomes.",
                }
            )
        elif "Session Recap agent" in system:
            content = json.dumps({"recap": "You discussed the negotiation.", "after_action_report": "Review your approach."})
        elif "Extract atomic facts" in system:
            content = json.dumps({"facts": []})
        else:
            content = "Sure, let's talk."
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(
        "negot.core.services.orchestrator.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.question_planner.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.templates.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.web_grounding.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.kg.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.sessions.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )
    monkeypatch.setattr(
        "negot.core.services.entity_proposer.acompletion_with_retry",
        _fake_acompletion_with_retry,
    )


async def _post_message_stream(
    client: AsyncClient,
    session_id: int,
    payload: dict,
    user_id: str,
) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    buffer = ""
    async with client.stream(
        "POST",
        f"/sessions/{session_id}/messages",
        json=payload,
        headers={"X-User-Id": user_id},
    ) as res:
        assert res.status_code == 200
        async for chunk in res.aiter_text():
            buffer += chunk
    for block in buffer.split("\n\n"):
        if not block.strip():
            continue
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if event:
            events.append((event, data))
    return events


@pytest.fixture()
async def app() -> FastAPI:
    """Create and initialise the FastAPI app for testing."""
    application = create_app()
    # Initialise DB schema
    await init_db_schema()
    return application


@pytest.mark.asyncio
async def test_create_session_and_message_flow(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a session with a salary negotiation topic
        res = await client.post("/sessions", json={"topic_text": "I want to negotiate my salary"}, headers={"X-User-Id": "1"})
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        session_id = data["session_id"]
        # Post a message
        events = await _post_message_stream(
            client,
            session_id,
            {"content": "I'd like to discuss my compensation."},
            "1",
        )
        done_payload = next(data for event, data in events if event == "done")
        msg_data = json.loads(done_payload)
        assert msg_data.get("counterparty_message") is not None
        # End the session
        res3 = await client.post(f"/sessions/{session_id}/end", headers={"X-User-Id": "1"})
        assert res3.status_code == 200
        recap = res3.json()
        assert "recap" in recap


@pytest.mark.asyncio
async def test_memory_review(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/sessions", json={"topic_text": "test"}, headers={"X-User-Id": "2"})
        session_id = res.json()["session_id"]
        # Post a message that yields no facts
        await _post_message_stream(
            client,
            session_id,
            {"content": "Hello"},
            "2",
        )
        # End session
        await client.post(f"/sessions/{session_id}/end", headers={"X-User-Id": "2"})
        # Memory review with no facts
        res2 = await client.post(
            f"/sessions/{session_id}/memory-review",
            json={"decisions": []},
            headers={"X-User-Id": "2"},
        )
        assert res2.status_code == 200
        assert res2.json()["updated_facts"] == []
