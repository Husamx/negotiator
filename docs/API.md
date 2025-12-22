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

Response (non-streaming):
- counterparty_message
- optional: coach_panel (premium)
- optional: grounding_pack (when run this turn)
- extracted_facts (session-only candidates)

Streaming variant:
- stream roleplay tokens
- premium: stream coach panel separately

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

## 7. Admin (internal)
- GET /admin/template-proposals
- POST /admin/template-proposals/{id}/approve|reject|edit
