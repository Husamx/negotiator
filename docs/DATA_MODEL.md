# Data Model (v0.1)

Defines persistence for:
- Sessions (chat)
- World graph (entities/relationships/facts)
- Visibility model (knowledge edges + priors + disclosures)
- Web grounding (search cache + grounding packs)
- Event sourcing (telemetry + training signals)

## 1. Core tables

### 1.1 users
- user_id (PK)
- created_at
- tier (standard|premium)
- consent flags (telemetry, raw_text_sharing, etc.)

### 1.2 sessions
- session_id (PK)
- user_id (FK)
- template_id
- title
- created_at, ended_at
- counterparty_style
- attached_entity_ids (join table recommended)

### 1.3 session_entities (join)
- session_id
- entity_id

### 1.4 messages
- message_id (PK)
- session_id (FK)
- role (user|counterparty|system|coach)
- content
- created_at
- llm_provider / llm_model / prompt_version (optional)
- token usage + safety flags (optional)

## 2. World graph tables

### 2.1 entities
- entity_id (PK)
- user_id (FK)
- type
- name
- attributes_json
- created_at, updated_at

### 2.2 relationships
- edge_id (PK)
- user_id (FK)
- src_entity_id
- rel_type
- dst_entity_id
- provenance fields
- timestamps

### 2.3 facts (atomic, reified)
- fact_id (PK)
- user_id (FK)
- subject_entity_id
- key
- value
- value_type
- unit (optional)
- scope (global|session_only)
- confidence
- provenance fields
- timestamps

## 3. Visibility / epistemics

### 3.1 knowledge_edges
Represents KNOWS(knower_entity -> fact).

- knowledge_edge_id (PK)
- user_id (FK)
- knower_entity_id (FK)
- fact_id (FK)
- status (confirmed|assumed|false_belief)   # do NOT store unknown
- confidence (0..1)
- source (user_told|observed|inferred|public|third_party)
- scope (global|session:<id>)
- timestamps
- provenance fields

### Sparse epistemic storage rule (prevents edge explosion)
Do NOT store explicit `unknown` edges for every (entity × fact) pair.
Absence of a knowledge_edges row implies UNKNOWN.
Store rows only for confirmed knowledge, user overrides, and optional false beliefs.
Visibility is computed at runtime using priors + disclosures.

### 3.2 priors (optional table or config)
Store relationship_type × fact_category priors as config or a small table:
- relationship_type
- fact_category
- likely_known (bool)
- default_confidence

### 3.3 disclosures (session scope)
Disclosure can be represented by:
- knowledge_edges with scope=session:<id>, or
- a session_disclosures join table:
  - session_id, knower_entity_id, fact_id, created_at

## 4. Web grounding tables (recommended)

### 4.1 grounding_runs
- grounding_run_id (PK)
- user_id (FK)
- session_id (nullable)
- trigger (setup|mid_chat|user_requested)
- decision_json (need_search reasons, budget)
- queries_json
- provider = "tavily"
- params_json (search_depth, max_results, topic, include_raw_content)
- created_at

### 4.2 grounding_sources
- grounding_source_id (PK)
- grounding_run_id (FK)
- url
- title
- snippet
- raw_content (optional; store only if needed and with consent)
- score (optional)
- retrieved_at

### 4.3 grounding_packs
- grounding_pack_id (PK)
- grounding_run_id (FK)
- pack_json (key_points with citations, disputed, unknowns, questions)
- created_at

### 4.4 grounding_cache (optional)
Cache by normalized_query + region:
- cache_key (PK)
- provider
- response_json
- expires_at

## 5. Provenance model (shared)
Apply to facts/relationships/knowledge_edges:
- source_type (user_entered|user_confirmed_extraction|model_extracted|inferred|external)
- source_ref (session_id/message_id/ui_form_id/import_id)
- model_version / prompt_version (optional)
- created_at, updated_at

## 6. Event sourcing (append-only)

### 6.1 events
- event_id (PK)
- user_id (FK)
- session_id (nullable)
- event_type
- payload_json
- created_at

### 6.2 tombstones (deletion ledger)
- tombstone_id
- user_id
- object_type
- object_id
- deleted_at
- reason
