# API (v0.1) — Contract Outline

## 1. Conventions
- JSON over HTTPS
- Streaming: SSE (recommended) or WebSocket (choose one)
- Tier gating enforced server-side

## 2. Sessions

### 2.1 Create session
`POST /sessions`

Request:
- topic_text (string)
- counterparty_style (optional)
- attached_entity_ids (optional list)
- channel (optional: EMAIL, DM, IN_PERSON_NOTES)

Response:
- session_id
- template_id
- proposed_entities (optional)
- intake_questions (list)
- optional: grounding_decision (if precomputed)

### 2.2 Post a message (roleplay)
`POST /sessions/{session_id}/messages`

Request:
- content (string)
- channel = "roleplay" (standard & premium)
- (premium only) channel="coach_private" for private notes
- enable_web_grounding (optional bool, default true)
- web_grounding_trigger (optional enum: auto|user_requested)   # server validates

Response (SSE streaming only):
- event: token (string)
- event: done (JSON payload)
  - counterparty_message
  - optional: coach_panel (premium)
  - optional: grounding_pack (when run this turn)
  - extracted_facts (session-only candidates)
  - strategy_selection (latest selection payload)
- event: error (JSON payload with detail)

Hard rule:
- channel="coach_private" MUST NOT update counterparty disclosure/knowledge state.

### 2.3 End session
`POST /sessions/{session_id}/end`
Response:
- Standard: recap (descriptive)
- Premium: after_action_report + recap

### 2.4 Memory review commit
`POST /sessions/{session_id}/memory-review`
Request:
- decisions: [{ fact_id, decision: save_global|save_session_only|discard }]
Response:
- updated KG summary
### 2.5 Intake submission
`POST /sessions/{session_id}/intake`

Request:
- questions (list)
- answers (object)
- summary (optional string)

Response:
- case_snapshot (object)
- strategy_selection (selection payload + selected_strategy_id)

### 2.6 Case snapshot
`GET /sessions/{session_id}/case-snapshot`

Response:
- case_snapshot payload for the session

### 2.7 Strategy selection
`GET /sessions/{session_id}/strategy/selection`
`POST /sessions/{session_id}/strategy/selection`

Notes:
- Strategy selection is created during intake submission.
- POST is idempotent and returns the existing selection if one already exists.

Response:
- selected_strategy_id
- selection_payload (ranked strategies + rationale)

### 2.8 Strategy execution
`POST /sessions/{session_id}/strategy/execute`

Request:
- strategy_id (optional; defaults to selected)
- inputs (object)

Response:
- artifacts
- case_patches
- judge_outputs
- trace

### 2.9 Route generation (Negotiation Canvas)
`GET /sessions/{session_id}/routes?parent_message_id=123`
`POST /sessions/{session_id}/routes/generate`
`POST /sessions/{session_id}/threads/{thread_id}/activate`
`POST /sessions/{session_id}/threads/{thread_id}/copy`
`PATCH /sessions/{session_id}/threads/{thread_id}`
`DELETE /sessions/{session_id}/threads/{thread_id}`

Request (generate):
- variant: LIKELY | RISK | BEST | ALT
- existing_routes: [{counterparty_response, action_label, rationale}]
- parent_message_id (optional)

Response:
- branch_id
- thread_id
- parent_message_id
- variant
- counterparty_response
- rationale
- action_label
- branch_label
- created_at
- is_active (optional)

## 3. Web grounding (explicit endpoint)
Optional explicit endpoint (useful for UI refresh/debug):
`POST /sessions/{session_id}/grounding`

Request:
- mode: auto|user_requested
- user_question (optional)
- region_hint (optional)
- max_queries (optional)
Response:
- grounding_pack
- sources
- budget_spent

## 4. Knowledge Graph (World)
- GET/POST/PATCH/DELETE /entities
- GET/POST/PATCH/DELETE /facts
- GET/POST/DELETE /relationships

## 5. Visibility (epistemics)
- GET/POST/PATCH/DELETE /knowledge-edges
Premium-only editing (Standard read-only at API level).

## 6. Templates
- GET /templates (official)
- GET /templates/drafts (per-user)
- POST /templates/proposals (enqueue review)

## 7. Strategies
- GET /strategies (list enabled strategies)
- GET /strategies/{strategy_id} (full strategy template)

## 8. Admin (internal)
- GET /admin/template-proposals
- POST /admin/template-proposals/{id}/approve|reject|edit
