"""
Streamlit UI for the Negotiation Companion (v0.1).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
import streamlit as st


API_BASE_URL = "http://localhost:8000"
AUTO_START_ROLEPLAY_MESSAGE = "Let's begin the roleplay."


def _headers(user_id: str) -> Dict[str, str]:
    return {"X-User-Id": user_id}


def _api_get(path: str, user_id: str, params: Optional[dict] = None) -> httpx.Response:
    with httpx.Client(timeout=None) as client:
        return client.get(f"{API_BASE_URL}{path}", headers=_headers(user_id), params=params)


def _api_post(
    path: str,
    user_id: str,
    payload: Optional[dict] = None,
    params: Optional[dict] = None,
) -> httpx.Response:
    with httpx.Client(timeout=None) as client:
        return client.post(
            f"{API_BASE_URL}{path}", headers=_headers(user_id), json=payload or {}, params=params
        )


def _api_patch(path: str, user_id: str, payload: Optional[dict] = None) -> httpx.Response:
    with httpx.Client(timeout=None) as client:
        return client.patch(f"{API_BASE_URL}{path}", headers=_headers(user_id), json=payload or {})


def _api_delete(path: str, user_id: str) -> httpx.Response:
    with httpx.Client(timeout=None) as client:
        return client.delete(f"{API_BASE_URL}{path}", headers=_headers(user_id))


def _iter_sse_events(response: httpx.Response) -> Iterable[Tuple[str, str]]:
    event = None
    for raw_line in response.iter_lines():
        if raw_line is None:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line == "":
            event = None
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
            yield (event or "message"), data


def _ensure_user_state() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = "1"
    if "user_tier" not in st.session_state:
        st.session_state.user_tier = "standard"
    if "consent_telemetry" not in st.session_state:
        st.session_state.consent_telemetry = False
    if "consent_raw_text" not in st.session_state:
        st.session_state.consent_raw_text = False
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "new_session_step" not in st.session_state:
        st.session_state.new_session_step = 1
    if "new_session" not in st.session_state:
        st.session_state.new_session = {
            "topic_text": "",
            "counterparty_style": "neutral",
            "channel": "DM",
            "entity_ids": [],
            "questions": [],
            "answers": {},
        }
    if "new_session_entity_select_pending" not in st.session_state:
        st.session_state.new_session_entity_select_pending = []
    if "intake_queue" not in st.session_state:
        st.session_state.intake_queue = []
    if "intake_answers" not in st.session_state:
        st.session_state.intake_answers = {}
    if "intake_transcript" not in st.session_state:
        st.session_state.intake_transcript = []
    if "intake_session_id" not in st.session_state:
        st.session_state.intake_session_id = None
    if "intake_summary" not in st.session_state:
        st.session_state.intake_summary = None
    if "intake_autostart_pending" not in st.session_state:
        st.session_state.intake_autostart_pending = False
    if "allow_web_grounding" not in st.session_state:
        st.session_state.allow_web_grounding = True
    if "session_recap" not in st.session_state:
        st.session_state.session_recap = None
    if "strategy_selection" not in st.session_state:
        st.session_state.strategy_selection = None
    if "strategy_execution" not in st.session_state:
        st.session_state.strategy_execution = None


def _load_user_profile() -> None:
    resp = _api_get("/users/me", st.session_state.user_id)
    if resp.status_code == 200:
        data = resp.json()
        st.session_state.user_tier = data.get("tier", st.session_state.user_tier)
        st.session_state.consent_telemetry = data.get(
            "consent_telemetry", st.session_state.consent_telemetry
        )
        st.session_state.consent_raw_text = data.get(
            "consent_raw_text", st.session_state.consent_raw_text
        )


def _update_tier(tier: str) -> None:
    resp = _api_patch("/users/me/tier", st.session_state.user_id, {"tier": tier})
    if resp.status_code == 200:
        st.session_state.user_tier = resp.json().get("tier", tier)


def _update_consents(consent_telemetry: bool, consent_raw_text: bool) -> None:
    resp = _api_patch(
        "/users/me/consent",
        st.session_state.user_id,
        {"consent_telemetry": consent_telemetry, "consent_raw_text": consent_raw_text},
    )
    if resp.status_code == 200:
        data = resp.json()
        st.session_state.consent_telemetry = data.get(
            "consent_telemetry", consent_telemetry
        )
        st.session_state.consent_raw_text = data.get(
            "consent_raw_text", consent_raw_text
        )


def _reset_new_session() -> None:
    st.session_state.new_session_step = 1
    st.session_state.new_session = {
        "topic_text": "",
        "counterparty_style": "neutral",
        "channel": "DM",
        "entity_ids": [],
        "questions": [],
        "answers": {},
    }
    st.session_state.new_session_entity_select_pending = []
    if "new_session_entity_select" in st.session_state:
        del st.session_state["new_session_entity_select"]


def _attribute_rows(state_key: str, initial: Optional[dict] = None) -> Dict[str, str]:
    if state_key not in st.session_state:
        rows = [
            {"key": key, "value": str(value)}
            for key, value in (initial or {}).items()
        ]
        if not rows:
            rows = [{"key": "", "value": ""}]
        st.session_state[state_key] = rows
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, str]] = []
    for idx, row in enumerate(rows):
        col_key, col_val, col_del = st.columns([3, 3, 1])
        key_val = col_key.text_input(
            f"Key {idx + 1}",
            value=row.get("key", ""),
            key=f"{state_key}_key_{idx}",
            label_visibility="collapsed",
            placeholder="key",
        )
        val_val = col_val.text_input(
            f"Value {idx + 1}",
            value=row.get("value", ""),
            key=f"{state_key}_val_{idx}",
            label_visibility="collapsed",
            placeholder="value",
        )
        remove = col_del.button("Remove", key=f"{state_key}_remove_{idx}")
        if not remove:
            updated_rows.append({"key": key_val, "value": val_val})
    if st.button("Add attribute", key=f"{state_key}_add"):
        updated_rows.append({"key": "", "value": ""})
    st.session_state[state_key] = updated_rows
    attrs: Dict[str, str] = {}
    for row in updated_rows:
        key = row.get("key", "").strip()
        if key:
            attrs[key] = row.get("value", "")
    return attrs


def _list_input(label: str, state_key: str, help_text: Optional[str] = None) -> List[str]:
    raw = st.text_area(label, key=state_key, help=help_text)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _build_intake_summary(
    topic_text: str,
    template_id: Optional[str],
    questions: List[str],
    answers: Dict[str, str],
) -> str:
    lines = []
    if topic_text:
        lines.append(f"Topic: {topic_text}")
    if template_id:
        lines.append(f"Template: {template_id}")
    for question in questions:
        answer = answers.get(question, "")
        lines.append(f"{question} Answer: {answer}")
    return "Intake summary:\n" + "\n".join(lines)


def _load_session_history(session_id: int) -> List[Dict[str, Any]]:
    resp = _api_get(f"/sessions/{session_id}", st.session_state.user_id)
    if resp.status_code != 200:
        st.error("Failed to load session history.")
        return []
    data = resp.json()
    messages = []
    for msg in data.get("messages", []):
        role = msg.get("role")
        if role == "counterparty":
            display_role = "assistant"
        elif role == "user":
            display_role = "user"
        else:
            continue
        messages.append({"role": display_role, "content": msg.get("content", "")})
    return messages


def _set_active_session(session_id: int) -> None:
    st.session_state.session_id = session_id
    st.session_state.messages = _load_session_history(session_id)
    st.session_state.session_recap = None
    st.session_state.strategy_selection = None
    st.session_state.strategy_execution = None


def _stream_roleplay_message(
    session_id: int,
    content: str,
    placeholder: st.delta_generator.DeltaGenerator,
    enable_web_grounding: bool,
) -> Tuple[str, Dict[str, Any]]:
    response_text = ""
    payload: Dict[str, Any] = {}
    error_detail: Optional[str] = None
    with httpx.Client(timeout=None) as client:
        with client.stream(
            "POST",
            f"{API_BASE_URL}/sessions/{session_id}/messages",
            params={"stream": "true"},
            json={
                "content": content,
                "channel": "roleplay",
                "enable_web_grounding": enable_web_grounding,
                "web_grounding_trigger": "auto",
            },
            headers=_headers(st.session_state.user_id),
        ) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                for event, data in _iter_sse_events(resp):
                    if event == "token":
                        try:
                            token = json.loads(data)
                        except json.JSONDecodeError:
                            token = data
                        response_text += token
                        placeholder.markdown(response_text)
                    elif event == "error":
                        try:
                            error_payload = json.loads(data)
                        except json.JSONDecodeError:
                            error_payload = {"detail": data}
                        error_detail = error_payload.get("detail", "Streaming error")
                        break
                    elif event == "done":
                        payload = json.loads(data)
            else:
                payload = resp.json()
                response_text = payload.get("counterparty_message", "") or ""
                placeholder.markdown(response_text)
    if error_detail:
        payload["error"] = error_detail
    return response_text, payload


def _render_user_controls() -> None:
    st.markdown("### User")
    user_id = st.text_input("User ID", value=st.session_state.user_id)
    if user_id != st.session_state.user_id:
        st.session_state.user_id = user_id
        st.session_state.session_id = None
        st.session_state.messages = []
        _load_user_profile()
    tier = st.selectbox(
        "Tier",
        options=["standard", "premium"],
        index=["standard", "premium"].index(st.session_state.user_tier),
        key="user_tier_select",
    )
    if tier != st.session_state.user_tier:
        _update_tier(tier)
    st.markdown("**Consent**")
    consent_telemetry = st.checkbox(
        "Share anonymized telemetry", value=st.session_state.consent_telemetry
    )
    consent_raw_text = st.checkbox(
        "Share raw conversation text", value=st.session_state.consent_raw_text
    )
    if (
        consent_telemetry != st.session_state.consent_telemetry
        or consent_raw_text != st.session_state.consent_raw_text
    ):
        _update_consents(consent_telemetry, consent_raw_text)


def _render_sessions_panel() -> None:
    st.markdown("### Sessions")
    resp = _api_get("/sessions", st.session_state.user_id)
    if resp.status_code != 200:
        st.error("Failed to load sessions.")
        return
    sessions = resp.json()
    if not sessions:
        st.info("No sessions yet.")
        return
    for session in sessions:
        is_active = session.get("id") == st.session_state.session_id
        title = session.get("title") or "Session"
        status = "Ended" if session.get("ended_at") else "Active"
        st.markdown(f"**{title}**")
        st.caption(
            f"Session {session.get('id')} | {status} | Template {session.get('template_id')}"
        )
        if session.get("topic_text"):
            st.caption(session.get("topic_text"))
        label = "Open (active)" if is_active else "Open"
        if st.button(label, key=f"open_session_{session['id']}"):
            _set_active_session(session["id"])


def _render_new_session_panel() -> None:
    st.markdown("### New Session")
    step = st.session_state.new_session_step
    if step == 1:
        st.markdown("**Step 1: Topic**")
        topic = st.text_area(
            "Describe your negotiation topic (1-2 sentences)",
            value=st.session_state.new_session["topic_text"],
        )
        style = st.selectbox(
            "Counterparty style",
            options=["polite", "neutral", "tough", "busy", "defensive"],
            index=["polite", "neutral", "tough", "busy", "defensive"].index(
                st.session_state.new_session["counterparty_style"]
            ),
            key="new_session_style_select",
        )
        channel = st.selectbox(
            "Channel",
            options=["EMAIL", "DM", "IN_PERSON_NOTES"],
            index=["EMAIL", "DM", "IN_PERSON_NOTES"].index(
                st.session_state.new_session.get("channel", "DM")
            ),
            key="new_session_channel_select",
        )
        st.session_state.new_session["topic_text"] = topic
        st.session_state.new_session["counterparty_style"] = style
        st.session_state.new_session["channel"] = channel
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reset", key="new_session_reset_step1"):
                _reset_new_session()
        with col2:
            if st.button("Next", type="primary", key="new_session_next_step1") and topic:
                st.session_state.new_session_step = 2
    elif step == 2:
        st.markdown("**Step 2: Entities**")
        entities_resp = _api_get("/entities", st.session_state.user_id)
        entities = entities_resp.json() if entities_resp.status_code == 200 else []
        entity_map = {f"{ent['name']} ({ent['type']})": ent["id"] for ent in entities}
        pending = [
            label
            for label in st.session_state.new_session_entity_select_pending
            if label in entity_map
        ]
        if pending:
            current = st.session_state.get("new_session_entity_select", [])
            merged = list(dict.fromkeys(current + pending))
            st.session_state["new_session_entity_select"] = merged
            st.session_state.new_session_entity_select_pending = []
        elif st.session_state.new_session_entity_select_pending:
            st.session_state.new_session_entity_select_pending = []
        selected_labels = st.multiselect(
            "Attach existing entities",
            options=list(entity_map.keys()),
            default=[
                label
                for label, eid in entity_map.items()
                if eid in st.session_state.new_session["entity_ids"]
            ],
            key="new_session_entity_select",
        )
        st.session_state.new_session["entity_ids"] = [
            entity_map[label] for label in selected_labels
        ]
        with st.expander("Create new entity", expanded=False):
            ent_type = st.text_input("Type", value="person", key="new_session_entity_type")
            ent_name = st.text_input("Name", key="new_session_entity_name")
            st.markdown("Attributes")
            ent_attrs = _attribute_rows("new_entity_attrs")
            if st.button("Create entity", key="new_session_entity_create"):
                if not ent_name:
                    st.error("Entity name is required.")
                else:
                    resp = _api_post(
                        "/entities",
                        st.session_state.user_id,
                        {"type": ent_type, "name": ent_name, "attributes": ent_attrs},
                    )
                    if resp.status_code == 201:
                        entity = resp.json()
                        entity_id = entity.get("id")
                        if entity_id is not None:
                            current_ids = st.session_state.new_session["entity_ids"]
                            if entity_id not in current_ids:
                                st.session_state.new_session["entity_ids"] = current_ids + [entity_id]
                            label = f"{entity.get('name')} ({entity.get('type')})"
                            if label:
                                st.session_state.new_session_entity_select_pending = [label]
                        st.success("Entity created and attached.")
                        st.rerun()
                    else:
                        st.error(resp.text)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back", key="new_session_back_step2"):
                st.session_state.new_session_step = 1
        with col2:
            if st.button("Next", type="primary", key="new_session_next_step2"):
                st.session_state.new_session_step = 3
    elif step == 3:
        st.markdown("**Step 3: Create session**")
        payload = {
            "topic_text": st.session_state.new_session["topic_text"],
            "counterparty_style": st.session_state.new_session["counterparty_style"],
            "attached_entity_ids": st.session_state.new_session["entity_ids"],
            "channel": st.session_state.new_session.get("channel", "DM"),
        }
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Create session", type="primary", key="new_session_create_session"):
                resp = _api_post("/sessions", st.session_state.user_id, payload)
                if resp.status_code == 200:
                    data = resp.json()
                    session_id = data.get("session_id")
                    st.session_state.intake_queue = data.get("intake_questions", [])
                    st.session_state.intake_answers = {}
                    st.session_state.intake_transcript = []
                    st.session_state.intake_session_id = session_id
                    st.session_state.intake_summary = None
                    _set_active_session(session_id)
                    _reset_new_session()
                    st.success("Session created and opened.")
                else:
                    st.error(resp.text)
        with col2:
            if st.button("Back", key="new_session_back_step3"):
                st.session_state.new_session_step = 2
    else:
        st.info("Intake questions now appear in the chat panel.")
        if st.button("Back to start", type="primary", key="new_session_back_start"):
            _reset_new_session()


def _render_session_controls(session_data: Dict[str, Any]) -> None:
    session_id = st.session_state.session_id
    if not session_id:
        return
    st.markdown("**Session controls**")
    col1, col2 = st.columns([2, 1])
    with col1:
        style = st.selectbox(
            "Counterparty style",
            options=["polite", "neutral", "tough", "busy", "defensive"],
            index=["polite", "neutral", "tough", "busy", "defensive"].index(
                session_data.get("counterparty_style") or "neutral"
            ),
            key=f"session_style_select_{session_id}",
        )
        if st.button("Apply style"):
            _api_patch(
                f"/sessions/{session_id}",
                st.session_state.user_id,
                {"counterparty_style": style},
            )
    with col2:
        st.checkbox(
            "Allow web grounding",
            value=st.session_state.allow_web_grounding,
            key="allow_web_grounding",
        )
    entities_resp = _api_get("/entities", st.session_state.user_id)
    entities = entities_resp.json() if entities_resp.status_code == 200 else []
    entity_map = {f"{ent['name']} ({ent['type']})": ent["id"] for ent in entities}
    attached_ids = [ent["id"] for ent in session_data.get("attached_entities", [])]
    attached_labels = [
        label for label, eid in entity_map.items() if eid in attached_ids
    ]
    selection = st.multiselect(
        "Entity tray",
        options=list(entity_map.keys()),
        default=attached_labels,
    )
    selected_ids = [entity_map[label] for label in selection]
    if st.button("Update attachments"):
        attach_ids = [eid for eid in selected_ids if eid not in attached_ids]
        detach_ids = [eid for eid in attached_ids if eid not in selected_ids]
        if attach_ids:
            _api_post(
                f"/sessions/{session_id}/attach",
                st.session_state.user_id,
                {"entity_ids": attach_ids},
            )
        if detach_ids:
            _api_post(
                f"/sessions/{session_id}/detach",
                st.session_state.user_id,
                {"entity_ids": detach_ids},
            )


def _render_session_event_log(session_id: int) -> None:
    with st.expander("Orchestration log", expanded=False):
        resp = _api_get(f"/sessions/{session_id}/events", st.session_state.user_id)
        if resp.status_code != 200:
            st.error("Failed to load event log.")
            return
        events = resp.json()
        if not events:
            st.caption("No events yet.")
            return
        for event in events[-50:]:
            event_type = event.get("event_type", "UNKNOWN")
            created_at = event.get("created_at", "")
            st.markdown(f"**{event_type}** · {created_at}")
            payload = event.get("payload") or {}
            if payload:
                st.json(payload)


def _render_chat_panel() -> None:
    st.markdown("### Chat")
    session_id = st.session_state.session_id
    if not session_id:
        st.info("Select or create a session to start chatting.")
        return
    session_resp = _api_get(f"/sessions/{session_id}", st.session_state.user_id)
    if session_resp.status_code != 200:
        st.error("Failed to load session.")
        return
    session_data = session_resp.json()
    title = session_data.get("title") or "Session"
    st.markdown(f"**Session {session_id}: {title}**")
    if session_data.get("topic_text"):
        st.caption(session_data.get("topic_text"))
    st.caption(
        f"Template: {session_data.get('template_id')} | Style: {session_data.get('counterparty_style') or 'neutral'}"
    )
    selection_data = st.session_state.strategy_selection
    if not selection_data:
        selection_resp = _api_get(
            f"/sessions/{session_id}/strategy/selection", st.session_state.user_id
        )
        if selection_resp.status_code == 200:
            record = selection_resp.json()
            selection_data = record.get("selection_payload") or {}
            selection_data["selected_strategy_id"] = record.get("selected_strategy_id")
            st.session_state.strategy_selection = selection_data
    if selection_data:
        selected_id = selection_data.get("selected_strategy_id")
        if selected_id:
            st.caption(f"Active strategy: {selected_id}")
    with st.expander("Strategy", expanded=False):
        _render_strategy_panel(show_header=False)
    _render_session_controls(session_data)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Reload history"):
            st.session_state.messages = _load_session_history(session_id)
    with col2:
        if st.button("End session"):
            resp = _api_post(f"/sessions/{session_id}/end", st.session_state.user_id)
            if resp.status_code == 200:
                recap = resp.json()
                st.session_state.session_recap = recap.get("recap")
                st.success("Session ended.")
            else:
                st.error(resp.text)
    if session_data.get("ended_at"):
        st.warning("This session has ended. Start a new session to continue.")
        if st.session_state.session_recap:
            st.markdown(st.session_state.session_recap)
        return
    intake_questions = []
    if st.session_state.intake_session_id == session_id:
        intake_questions = st.session_state.intake_queue
    if intake_questions:
        st.info("Answer intake questions to start the roleplay.")
        answers = st.session_state.intake_answers
        next_question = None
        for question in intake_questions:
            with st.chat_message("assistant"):
                st.markdown(question)
            answer = answers.get(question)
            if answer:
                with st.chat_message("user"):
                    st.markdown(answer)
            else:
                next_question = question
                break
        if next_question:
            response = st.chat_input("Answer intake question")
            if response:
                answers[next_question] = response
                st.session_state.intake_answers = answers
                st.session_state.intake_transcript.extend(
                    [
                        {"role": "assistant", "content": next_question},
                        {"role": "user", "content": response},
                    ]
                )
                if len(answers) >= len(intake_questions):
                    st.session_state.intake_summary = _build_intake_summary(
                        session_data.get("topic_text", ""),
                        session_data.get("template_id"),
                        intake_questions,
                        answers,
                    )
                    intake_payload = {
                        "questions": intake_questions,
                        "answers": answers,
                        "summary": st.session_state.intake_summary,
                    }
                    intake_resp = _api_post(
                        f"/sessions/{session_id}/intake",
                        st.session_state.user_id,
                        intake_payload,
                    )
                    if intake_resp.status_code == 200:
                        intake_data = intake_resp.json()
                        st.session_state.strategy_selection = intake_data.get(
                            "strategy_selection"
                        )
                    else:
                        st.error(intake_resp.text)
                    st.session_state.intake_queue = []
                    st.session_state.intake_autostart_pending = True
                st.rerun()
        return
    if (
        st.session_state.intake_session_id == session_id
        and st.session_state.intake_transcript
    ):
        for message in st.session_state.intake_transcript:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("coach_panel"):
                with st.expander("Coach Panel", expanded=False):
                    st.json(message["coach_panel"])
            if message.get("grounding_pack"):
                with st.expander("Grounding Pack", expanded=False):
                    st.json(message["grounding_pack"])
    prompt = st.chat_input("Send a message")
    if (
        not prompt
        and st.session_state.intake_autostart_pending
        and st.session_state.intake_summary
        and st.session_state.intake_session_id == session_id
        and not st.session_state.messages
    ):
        prompt = AUTO_START_ROLEPLAY_MESSAGE
    if prompt:
        if st.session_state.intake_autostart_pending:
            st.session_state.intake_autostart_pending = False
        outbound = prompt
        if st.session_state.intake_summary:
            outbound = f"{st.session_state.intake_summary}\n\nUser message: {prompt}"
            st.session_state.intake_summary = None
            st.session_state.intake_session_id = None
            st.session_state.intake_transcript = []
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            placeholder = st.empty()
            response_text, payload = _stream_roleplay_message(
                session_id,
                outbound,
                placeholder,
                st.session_state.allow_web_grounding,
            )
            if payload.get("error"):
                st.error(payload["error"])
            if payload.get("coach_panel"):
                with st.expander("Coach Panel", expanded=False):
                    st.json(payload["coach_panel"])
            if payload.get("grounding_pack"):
                with st.expander("Grounding Pack", expanded=False):
                    st.json(payload["grounding_pack"])
            if payload.get("strategy_selection"):
                st.session_state.strategy_selection = payload["strategy_selection"]
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response_text,
                "coach_panel": payload.get("coach_panel"),
                "grounding_pack": payload.get("grounding_pack"),
            }
        )
    _render_session_event_log(session_id)


def _render_memory_review_panel() -> None:
    st.markdown("### Memory Review")
    session_id = st.session_state.session_id
    if not session_id:
        st.info("Select a session to review facts.")
        return
    resp = _api_get(f"/sessions/{session_id}/facts", st.session_state.user_id)
    if resp.status_code != 200:
        st.error("Failed to load session facts.")
        return
    facts = resp.json()
    if not facts:
        st.info("No extracted facts to review.")
        return
    decisions = []
    for fact in facts:
        st.markdown(f"**{fact['key']}** = {fact['value']}")
        st.caption(f"Source: {fact.get('source_ref')}")
        decision = st.selectbox(
            f"Decision for fact {fact['id']}",
            options=["save_global", "save_session_only", "discard"],
            key=f"fact_decision_{fact['id']}",
        )
        decisions.append({"fact_id": fact["id"], "decision": decision})
    if st.button("Submit decisions", type="primary"):
        resp = _api_post(
            f"/sessions/{session_id}/memory-review",
            st.session_state.user_id,
            {"decisions": decisions},
        )
        if resp.status_code == 200:
            st.success("Memory review submitted.")
        else:
            st.error(resp.text)


def _render_session_kg_snapshot(session_data: Dict[str, Any]) -> None:
    st.markdown("### Session KG")
    attached_entities = session_data.get("attached_entities", [])
    if not attached_entities:
        st.info("No attached entities for this session.")
        return
    attached_ids = [ent.get("id") for ent in attached_entities]
    st.markdown("**Attached Entities**")
    st.json(attached_entities)
    facts_resp = _api_get("/facts", st.session_state.user_id)
    if facts_resp.status_code == 200:
        all_facts = facts_resp.json()
        scoped = [
            fact for fact in all_facts if fact.get("subject_entity_id") in attached_ids
        ]
        st.markdown("**Facts for Attached Entities**")
        st.json(scoped)
    rel_resp = _api_get("/relationships", st.session_state.user_id)
    if rel_resp.status_code == 200:
        relationships = rel_resp.json()
        scoped_rel = [
            rel
            for rel in relationships
            if rel.get("src_entity_id") in attached_ids
            or rel.get("dst_entity_id") in attached_ids
        ]
        st.markdown("**Relationships (attached)**")
        st.json(scoped_rel)


def _render_orchestration_panel() -> None:
    st.markdown("### Orchestration")
    session_id = st.session_state.session_id
    if not session_id:
        st.info("Select a session to see orchestration context.")
        return
    events_resp = _api_get(f"/sessions/{session_id}/events", st.session_state.user_id)
    if events_resp.status_code != 200:
        st.error("Failed to load events.")
        return
    events = events_resp.json()
    prompt_event = None
    for event in reversed(events):
        if event.get("event_type") == "ORCHESTRATION_CONTEXT_BUILT":
            prompt_event = event
            break
    if not prompt_event:
        st.info("No prompt context recorded yet.")
        return
    payload = prompt_event.get("payload") or {}
    history_count = payload.get("history_count")
    history_limit = payload.get("history_limit")
    if history_count is not None:
        st.caption(f"History included: {history_count}/{history_limit}")
    messages = payload.get("messages", [])
    if not messages:
        st.info("Prompt messages not available.")
    else:
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            st.markdown(f"**{role}**")
            st.write(content)
    with st.expander("Raw prompt payload", expanded=False):
        st.json(payload)


def _render_strategy_panel(show_header: bool = True) -> None:
    if show_header:
        st.markdown("### Strategy")
    session_id = st.session_state.session_id
    if not session_id:
        st.info("Select a session to view strategies.")
        return
    selection = st.session_state.strategy_selection
    if not selection:
        resp = _api_get(f"/sessions/{session_id}/strategy/selection", st.session_state.user_id)
        if resp.status_code == 200:
            record = resp.json()
            selection = record.get("selection_payload") or {}
            selection["selected_strategy_id"] = record.get("selected_strategy_id")
            st.session_state.strategy_selection = selection
        else:
            selection = None
    if not selection:
        st.info("No strategy selected yet.")
        return
    selected_id = selection.get("selected_strategy_id")
    ranked = selection.get("response", {}).get("ranked_strategies", [])
    if not selected_id and ranked:
        selected_id = ranked[0].get("strategy_id")
    if not selected_id:
        st.info("Strategy selection is incomplete.")
        return
    st.caption(f"Selected strategy: {selected_id}")
    strat_resp = _api_get(f"/strategies/{selected_id}", st.session_state.user_id)
    if strat_resp.status_code != 200:
        st.error("Failed to load strategy details.")
        return
    strategy = strat_resp.json()
    st.markdown(f"**{strategy.get('name')}**")
    if strategy.get("summary"):
        st.caption(strategy.get("summary"))
    if strategy.get("goal"):
        st.caption(f"Goal: {strategy.get('goal')}")
    if ranked:
        with st.expander("Ranking details", expanded=False):
            st.json(ranked)
    inputs_payload: Dict[str, Any] = {}
    for input_def in strategy.get("inputs", []):
        key = input_def.get("key")
        if not key:
            continue
        label = input_def.get("label") or key
        help_text = input_def.get("help")
        input_type = input_def.get("type")
        state_key = f"strategy_input_{session_id}_{key}"
        default_val = input_def.get("default")
        if input_type == "STRING":
            value = st.text_input(label, value=str(default_val or ""), key=state_key, help=help_text)
        elif input_type == "NUMBER":
            value = st.number_input(label, value=float(default_val or 0), key=state_key, help=help_text)
        elif input_type == "BOOLEAN":
            value = st.checkbox(label, value=bool(default_val) if default_val is not None else False, key=state_key)
        elif input_type == "MONEY":
            amount_key = f"{state_key}_amount"
            currency_key = f"{state_key}_currency"
            amount = st.number_input(f"{label} amount", value=0.0, key=amount_key)
            currency = st.text_input(f"{label} currency", value="USD", key=currency_key)
            value = {"amount": amount, "currency": currency}
        elif input_type == "ENUM":
            enum_values = input_def.get("enum_values") or []
            if enum_values:
                value = st.selectbox(label, options=enum_values, key=state_key)
            else:
                value = st.text_input(label, value=str(default_val or ""), key=state_key, help=help_text)
        elif input_type in {"STRING_LIST", "ISSUE_LIST", "PACKAGE_LIST"}:
            value = _list_input(label, state_key, help_text=help_text)
        else:
            value = st.text_input(label, value=str(default_val or ""), key=state_key, help=help_text)
        inputs_payload[key] = value
    if st.button("Execute strategy", type="primary", key=f"execute_strategy_{session_id}"):
        resp = _api_post(
            f"/sessions/{session_id}/strategy/execute",
            st.session_state.user_id,
            {"strategy_id": selected_id, "inputs": inputs_payload},
        )
        if resp.status_code == 200:
            st.session_state.strategy_execution = resp.json()
        else:
            st.error(resp.text)
    if st.session_state.strategy_execution:
        with st.expander("Execution output", expanded=True):
            st.json(st.session_state.strategy_execution)


def _render_kg_manager_panel() -> None:
    st.markdown("### Knowledge Graph")
    tab_entities, tab_facts, tab_relationships, tab_edges = st.tabs(
        ["Entities", "Facts", "Relationships", "Knowledge Edges"]
    )
    with tab_entities:
        resp = _api_get("/entities", st.session_state.user_id)
        entities = resp.json() if resp.status_code == 200 else []
        if entities:
            st.dataframe(entities, use_container_width=True)
            options = {f"{ent['name']} ({ent['id']})": ent for ent in entities}
            selected_label = st.selectbox(
                "Select entity to edit",
                options=list(options.keys()),
                key="kg_entity_select",
            )
            selected_entity = options[selected_label]
            new_name = st.text_input(
                "New name",
                value=selected_entity["name"],
                key=f"ent_edit_name_{selected_entity['id']}",
            )
            st.markdown("Attributes")
            attrs = _attribute_rows(
                f"ent_edit_attrs_{selected_entity['id']}",
                initial=selected_entity.get("attributes") or {},
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button(
                    "Update entity", key=f"ent_update_{selected_entity['id']}"
                ):
                    resp = _api_patch(
                        f"/entities/{selected_entity['id']}",
                        st.session_state.user_id,
                        {"name": new_name, "attributes": attrs},
                    )
                    if resp.status_code == 200:
                        st.success("Entity updated.")
                    else:
                        st.error(resp.text)
            with col2:
                if st.button(
                    "Delete entity", key=f"ent_delete_{selected_entity['id']}"
                ):
                    resp = _api_delete(
                        f"/entities/{selected_entity['id']}", st.session_state.user_id
                    )
                    if resp.status_code == 204:
                        st.warning("Entity deleted.")
                    else:
                        st.error(resp.text)
        with st.expander("Create entity", expanded=False):
            ent_type = st.text_input("Type", key="kg_ent_type")
            ent_name = st.text_input("Name", key="kg_ent_name")
            st.markdown("Attributes")
            ent_attrs = _attribute_rows("kg_entity_attrs")
            if st.button("Create entity", key="kg_ent_create"):
                if not ent_name:
                    st.error("Entity name is required.")
                else:
                    resp = _api_post(
                        "/entities",
                        st.session_state.user_id,
                        {"type": ent_type, "name": ent_name, "attributes": ent_attrs},
                    )
                    if resp.status_code == 201:
                        st.success("Entity created.")
                    else:
                        st.error(resp.text)
    with tab_facts:
        resp = _api_get("/facts", st.session_state.user_id)
        facts = resp.json() if resp.status_code == 200 else []
        if facts:
            st.dataframe(facts, use_container_width=True)
            fact_options = {
                f"{fact['key']} ({fact['id']})": fact for fact in facts
            }
            selected_label = st.selectbox(
                "Select fact to edit",
                options=list(fact_options.keys()),
                key="kg_fact_select",
            )
            selected_fact = fact_options[selected_label]
            new_key = st.text_input(
                "New key", value=selected_fact["key"], key="fact_edit_key"
            )
            new_value = st.text_input(
                "New value",
                value=selected_fact["value"],
                key="fact_edit_value",
            )
            new_scope = st.selectbox(
                "New scope",
                options=["global", "session"],
                index=0 if selected_fact["scope"] == "global" else 1,
                key="fact_edit_scope",
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Update fact", key="fact_update"):
                    resp = _api_patch(
                        f"/facts/{selected_fact['id']}",
                        st.session_state.user_id,
                        {"key": new_key, "value": new_value, "scope": new_scope},
                    )
                    if resp.status_code == 200:
                        st.success("Fact updated.")
                    else:
                        st.error(resp.text)
            with col2:
                if st.button("Delete fact", key="fact_delete"):
                    resp = _api_delete(
                        f"/facts/{selected_fact['id']}", st.session_state.user_id
                    )
                    if resp.status_code == 204:
                        st.warning("Fact deleted.")
                    else:
                        st.error(resp.text)
        with st.expander("Create fact", expanded=False):
            subject_id = st.number_input("Subject entity ID", min_value=1, step=1)
            key = st.text_input("Key", key="fact_key")
            value = st.text_input("Value", key="fact_value")
            scope = st.selectbox(
                "Scope", options=["global", "session"], index=0, key="fact_create_scope"
            )
            if st.button("Create fact", key="fact_create"):
                resp = _api_post(
                    "/facts",
                    st.session_state.user_id,
                    {
                        "subject_entity_id": int(subject_id),
                        "key": key,
                        "value": value,
                        "scope": scope,
                    },
                )
                if resp.status_code == 201:
                    st.success("Fact created.")
                else:
                    st.error(resp.text)
    with tab_relationships:
        resp = _api_get("/relationships", st.session_state.user_id)
        relationships = resp.json() if resp.status_code == 200 else []
        if relationships:
            st.dataframe(relationships, use_container_width=True)
            rel_options = {
                f"{rel['rel_type']} ({rel['id']})": rel for rel in relationships
            }
            selected_label = st.selectbox(
                "Select relationship to delete",
                options=list(rel_options.keys()),
                key="kg_relationship_select",
            )
            selected_rel = rel_options[selected_label]
            if st.button("Delete relationship", key="rel_delete"):
                resp = _api_delete(
                    f"/relationships/{selected_rel['id']}", st.session_state.user_id
                )
                if resp.status_code == 204:
                    st.warning("Relationship deleted.")
                else:
                    st.error(resp.text)
        with st.expander("Create relationship", expanded=False):
            src_id = st.number_input(
                "Source entity ID", min_value=1, step=1, key="rel_src"
            )
            dst_id = st.number_input(
                "Destination entity ID", min_value=1, step=1, key="rel_dst"
            )
            rel_type = st.text_input("Relationship type", key="rel_type")
            if st.button("Create relationship", key="rel_create"):
                resp = _api_post(
                    "/relationships",
                    st.session_state.user_id,
                    {
                        "src_entity_id": int(src_id),
                        "dst_entity_id": int(dst_id),
                        "rel_type": rel_type,
                    },
                )
                if resp.status_code == 201:
                    st.success("Relationship created.")
                else:
                    st.error(resp.text)
    with tab_edges:
        resp = _api_get("/knowledge-edges", st.session_state.user_id)
        edges = resp.json() if resp.status_code == 200 else []
        if edges:
            st.dataframe(edges, use_container_width=True)
        if st.session_state.user_tier != "premium":
            st.info("Premium tier required to edit knowledge edges.")
        with st.expander("Create knowledge edge", expanded=False):
            knower_id = st.number_input(
                "Knower entity ID", min_value=1, step=1, key="edge_knower"
            )
            fact_id = st.number_input("Fact ID", min_value=1, step=1, key="edge_fact")
            status = st.text_input(
                "Status (confirmed/assumed/false_belief)", key="edge_status"
            )
            source = st.text_input(
                "Source (user_told/observed/inferred/public/third_party)",
                key="edge_source",
            )
            if st.button("Create knowledge edge", key="edge_create"):
                resp = _api_post(
                    "/knowledge-edges",
                    st.session_state.user_id,
                    {
                        "knower_entity_id": int(knower_id),
                        "fact_id": int(fact_id),
                        "status": status,
                        "confidence": 1.0,
                        "source": source,
                        "scope": "global",
                    },
                )
                if resp.status_code == 201:
                    st.success("Knowledge edge created.")
                else:
                    st.error(resp.text)
        if edges and st.session_state.user_tier == "premium":
            edge_options = {f"{edge['id']} ({edge['status']})": edge for edge in edges}
            selected_label = st.selectbox(
                "Select knowledge edge to delete",
                options=list(edge_options.keys()),
                key="kg_edge_select",
            )
            selected_edge = edge_options[selected_label]
            if st.button("Delete knowledge edge", key="edge_delete"):
                resp = _api_delete(
                    f"/knowledge-edges/{selected_edge['id']}", st.session_state.user_id
                )
                if resp.status_code == 204:
                    st.warning("Knowledge edge deleted.")
                else:
                    st.error(resp.text)


def _render_templates_panel() -> None:
    st.markdown("### Templates")
    drafts_resp = _api_get("/templates/drafts", st.session_state.user_id)
    if drafts_resp.status_code == 200:
        st.markdown("**Drafts**")
        st.json(drafts_resp.json())
    proposals_resp = _api_get("/templates/proposals", st.session_state.user_id)
    if proposals_resp.status_code == 200:
        st.markdown("**Proposals**")
        st.json(proposals_resp.json())


def _render_events_panel() -> None:
    st.markdown("### Event Timeline")
    session_id = st.session_state.session_id
    if not session_id:
        st.info("Select a session to view events.")
        return
    events_resp = _api_get(f"/sessions/{session_id}/events", st.session_state.user_id)
    if events_resp.status_code != 200:
        st.error("Failed to load events.")
        return
    events = events_resp.json()
    if not events:
        st.info("No events yet.")
        return
    st.dataframe(events, use_container_width=True)


def _render_admin_panel() -> None:
    st.markdown("### Admin Review")
    resp = _api_get("/admin/template-proposals", st.session_state.user_id)
    if resp.status_code != 200:
        st.error("Failed to load template proposals.")
        return
    proposals = resp.json()
    if not proposals:
        st.info("No template proposals.")
        return
    for proposal in proposals:
        st.markdown(
            f"**Proposal {proposal['id']}** (status: {proposal['status']})"
        )
        st.json(proposal.get("payload"))
        notes = st.text_area(
            "Reviewer notes", key=f"proposal_notes_{proposal['id']}"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Approve", key=f"proposal_approve_{proposal['id']}"):
                resp = _api_post(
                    f"/admin/template-proposals/{proposal['id']}/review",
                    st.session_state.user_id,
                    {"decision": "approve", "reviewer_notes": notes},
                )
                if resp.status_code == 200:
                    st.success("Approved.")
                else:
                    st.error(resp.text)
        with col2:
            if st.button("Reject", key=f"proposal_reject_{proposal['id']}"):
                resp = _api_post(
                    f"/admin/template-proposals/{proposal['id']}/review",
                    st.session_state.user_id,
                    {"decision": "reject", "reviewer_notes": notes},
                )
                if resp.status_code == 200:
                    st.warning("Rejected.")
                else:
                    st.error(resp.text)


def main() -> None:
    st.set_page_config(page_title="Negotiation Companion", layout="wide")
    st.title("Negotiation Companion")
    _ensure_user_state()
    _load_user_profile()

    left_col, center_col, right_col = st.columns([1.2, 2.2, 1.6])

    with left_col:
        _render_user_controls()
        st.markdown("---")
        _render_sessions_panel()
        st.markdown("---")
        _render_new_session_panel()

    with center_col:
        _render_chat_panel()

    with right_col:
        with st.expander("Memory Review", expanded=True):
            _render_memory_review_panel()
        with st.expander("Orchestration", expanded=True):
            _render_orchestration_panel()
        session_id = st.session_state.session_id
        if session_id:
            session_resp = _api_get(
                f"/sessions/{session_id}", st.session_state.user_id
            )
            if session_resp.status_code == 200:
                with st.expander("Session KG Snapshot", expanded=False):
                    _render_session_kg_snapshot(session_resp.json())
        with st.expander("Knowledge Graph Manager", expanded=False):
            _render_kg_manager_panel()
        with st.expander("Templates", expanded=False):
            _render_templates_panel()
        with st.expander("Event Timeline", expanded=False):
            _render_events_panel()
        with st.expander("Admin Review", expanded=False):
            _render_admin_panel()


if __name__ == "__main__":
    main()
