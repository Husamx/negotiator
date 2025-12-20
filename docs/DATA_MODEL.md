# Data Model (v0.1)

This doc defines the minimal persistence model for:
- Sessions (chat)
- World graph (entities/relationships/facts)
- Epistemic graph (who knows what)
- Event sourcing (telemetry + training signals)

## 1. Core tables

### 1.1 users
- `user_id` (PK)
- `created_at`
- `tier` (standard|premium)
- consent flags (telemetry, raw_text_sharing, etc.)

### 1.2 sessions
- `session_id` (PK)
- `user_id` (FK)
- `template_id` (FK or string)
- `title`
- `created_at`, `ended_at`
- `counterparty_style` (polite|neutral|tough|busy|defensive)
- `attached_entity_ids` (join table recommended)

### 1.3 session_entities (join)
- `session_id`
- `entity_id`

### 1.4 messages
- `message_id` (PK)
- `session_id` (FK)
- `role` (user|counterparty|system|coach)
- `content`
- `created_at`
- optional:
  - `llm_provider`
  - `llm_model`
  - `prompt_version`
  - `usage_tokens_in/out`
  - `safety_flags`

## 2. World graph tables

### 2.1 entities
- `entity_id` (PK)
- `user_id` (FK)
- `type` (Person|Company|Property|Lease|Offer|Custom|...)
- `name`
- `attributes_json` (typed KV)
- `created_at`, `updated_at`

### 2.2 relationships
- `edge_id` (PK)
- `user_id` (FK)
- `src_entity_id` (FK)
- `rel_type` (WORKS_AT|ROOMMATE_OF|DATING|PARENT_OF|RENTED_FROM|NEGOTIATING_WITH|...)
- `dst_entity_id` (FK)
- provenance fields (see section 4)
- timestamps

### 2.3 facts (atomic, reified)
- `fact_id` (PK)
- `user_id` (FK)
- `subject_entity_id` (FK)
- `key` (e.g., "salary.base")
- `value` (string/number/json)
- `value_type` (string|number|date|currency|json)
- `unit` (optional)
- `scope` (global|session_only)
- `valid_from`, `valid_to` (optional)
- `confidence` (0..1)
- provenance fields (see section 4)
- timestamps

## 3. Epistemic graph tables

### 3.1 knowledge_edges
Represents `KNOWS(knower_entity -> fact)`.

- `knowledge_edge_id` (PK)
- `user_id` (FK)
- `knower_entity_id` (FK)
- `fact_id` (FK)
- `status` (confirmed|assumed|unknown|false_belief)
- `confidence` (0..1)
- `source` (user_told|observed|inferred|public|third_party)
- `scope` (global|session:<id>)
- timestamps

## 4. Provenance model (shared)
Apply these columns to facts and relationships (and optionally entities):
- `source_type` (user_entered|user_confirmed_extraction|model_extracted|inferred|external)
- `source_ref` (session_id/message_id/ui_form_id/import_id)
- `extractor_version` / `model_version` / `prompt_version` (optional)
- `created_at`, `updated_at`

## 5. Event sourcing (append-only)

### 5.1 events
- `event_id` (PK)
- `user_id` (FK)
- `session_id` (nullable)
- `event_type` (string enum; see docs/EVENTS.md)
- `payload_json`
- `created_at`

### 5.2 tombstones (deletion ledger)
To ensure deletion propagates to training datasets:
- `tombstone_id`
- `user_id`
- `object_type` (entity|fact|message|relationship|knowledge_edge)
- `object_id`
- `deleted_at`
- `reason` (user_delete|gdpr_delete|...)

## 6. Indexing guidance
- `entities(user_id, type, name)`
- `facts(user_id, subject_entity_id, key)`
- `knowledge_edges(user_id, knower_entity_id, fact_id, scope)`
- `messages(session_id, created_at)`
- `events(user_id, created_at, event_type)`
