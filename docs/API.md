# API (v0.1) — Contract Outline

> This is an implementation-oriented outline. Exact fields may evolve, but endpoints and semantics should remain stable.

## 1. Conventions
- JSON over HTTPS
- Streaming: Server-Sent Events (SSE) or WebSocket (choose one in implementation)
- All objects are scoped by authenticated `user_id`
- Tier gating enforced server-side

## 2. Sessions

### 2.1 Create session
`POST /sessions`

Request:
- `topic_text` (string)
- `counterparty_style` (optional)
- `attached_entity_ids` (optional list)

Response:
- `session_id`
- `template_id`
- `proposed_entities` (optional)
- `intake_questions` (list)

### 2.2 Post a message (roleplay)
`POST /sessions/{session_id}/messages`

Request:
- `content` (string)
- `channel` = "roleplay" (standard & premium)
- (premium only) optionally `channel="coach_private"` for private notes to coach

Response (non-streaming):
- counterparty message (roleplay)
- optional extracted_facts (session-only suggestions)

Streaming variant:
- stream roleplay tokens as they are generated
- premium: optionally stream coach panel updates separately

### 2.3 End session
`POST /sessions/{session_id}/end`
Response:
- Standard: `recap` (descriptive)
- Premium: `after_action_report` + recap

### 2.4 Memory review commit
`POST /sessions/{session_id}/memory-review`

Request:
- `decisions`: list of { fact_id, decision: save_global|save_session_only|discard }

Response:
- updated KG summary

## 3. Knowledge Graph (World)

### 3.1 Entities
- `GET /entities?query=...`
- `POST /entities`
- `PATCH /entities/{entity_id}`
- `DELETE /entities/{entity_id}`

### 3.2 Facts
- `GET /facts?entity_id=...`
- `POST /facts`
- `PATCH /facts/{fact_id}`
- `DELETE /facts/{fact_id}`

### 3.3 Relationships
- `GET /relationships?entity_id=...`
- `POST /relationships`
- `DELETE /relationships/{edge_id}`

## 4. Epistemic graph
- `GET /knowledge-edges?knower_entity_id=...`
- `POST /knowledge-edges`
- `PATCH /knowledge-edges/{knowledge_edge_id}`
- `DELETE /knowledge-edges/{knowledge_edge_id}`

Premium-only: editing is allowed; Standard may be read-only at API level.

## 5. Templates
- `GET /templates` (official)
- `GET /templates/drafts` (per-user)
- `POST /templates/proposals` (create a proposal / enqueue review)

## 6. Admin (internal)
- `GET /admin/template-proposals`
- `POST /admin/template-proposals/{id}/approve`
- `POST /admin/template-proposals/{id}/reject`
- `POST /admin/template-proposals/{id}/edit`
