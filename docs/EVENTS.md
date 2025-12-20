# Events & Telemetry (v0.1)

Events are append-only records used for:
- product analytics
- debugging
- training signals (when user opted in)

## 1. Principles
- Emit events for every important decision point.
- Store immutable payloads; store derived aggregates separately.
- Respect user consent; honor deletion tombstones.

## 2. Event schema (common fields)
- `event_id`
- `user_id`
- `session_id` (nullable)
- `event_type`
- `created_at`
- `payload` (JSON)

## 3. Minimum event taxonomy (v0.1)

### Sessions
- `SESSION_CREATED`
- `SESSION_TEMPLATE_SELECTED`
- `SESSION_SETUP_QUESTION_ANSWERED`
- `SESSION_STARTED`
- `SESSION_ENDED`

### Messages
- `MESSAGE_USER_SENT`
- `MESSAGE_COUNTERPARTY_SENT`
- `MESSAGE_COACH_SENT` (premium)
- `MESSAGE_STREAM_STARTED/ENDED` (optional)

### Entity/KG
- `ENTITY_CREATED`
- `ENTITY_EDITED`
- `ENTITY_DELETED`
- `ENTITY_ATTACHED_TO_SESSION`
- `ENTITY_DETACHED_FROM_SESSION`

### Facts
- `FACT_EXTRACTED` (session-only candidate; includes confidence)
- `FACT_SUGGESTED_FOR_MEMORY`
- `FACT_CONFIRMED_FOR_MEMORY`
- `FACT_REJECTED_FOR_MEMORY`
- `FACT_EDITED`
- `FACT_DELETED`

### Relationships
- `RELATIONSHIP_CREATED`
- `RELATIONSHIP_DELETED`

### Epistemic (knowledge edges)
- `KNOWLEDGE_EDGE_SEEDED_FROM_PRIOR`
- `KNOWLEDGE_EDGE_UPDATED`
- `DISCLOSURE_IN_CHAT` (counterparty learned a fact)
- `PRIVATE_NOTE_TO_COACH` (premium; should not leak to counterparty)

### Templates
- `TEMPLATE_OTHER_TRIGGERED`
- `TEMPLATE_DRAFT_GENERATED`
- `TEMPLATE_PATCH_PROPOSED`
- `TEMPLATE_PROPOSAL_SUBMITTED_FOR_REVIEW`
- `TEMPLATE_PROPOSAL_APPROVED/REJECTED` (admin)

### Premium coaching
- `COACH_PANEL_SHOWN`
- `COACH_SUGGESTION_SHOWN`
- `COACH_SUGGESTION_USED`
- `COACH_SUGGESTION_RATED`

## 4. Consent gating
Events are separated into:
- **Essential**: required to operate the app for the user (always on)
- **Telemetry**: anonymized aggregates (opt-in)
- **Raw content**: includes message text or detailed transcripts (explicit opt-in)

## 5. Deletion propagation
When user deletes an object, record:
- tombstone entry (see DATA_MODEL.md)
- emit `OBJECT_DELETED` event (or type-specific deleted event)
Dataset builders must exclude tombstoned objects.
