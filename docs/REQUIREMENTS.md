# Requirements (v0.1)

> This document is the **source of truth** for what the app must do in v0.1.  
> It is intentionally detailed so devs can implement directly.

## 1. Product scope

### 1.1 Goal
Build a chat-based rehearsal app where:
- Every negotiation is a **chat session** (“role play”).
- Users can **reuse entities** (people, places, organizations, offers, leases, etc.) across sessions via a persistent **Knowledge Graph (KG)**.
- The role play stays realistic by modeling **who knows what** (epistemic knowledge).
- **Standard** is role play only; **Premium** adds coaching.
- The app can handle “Other” topics by generating **draft templates** (human-reviewed before becoming official).

### 1.2 Target audience (v0.1)
- People in their twenties.
- Primary use cases: interpersonal disagreements + everyday life negotiations.

### 1.3 Non-goals (v0.1)
- No automated outreach (sending emails/SMS in-app).
- No multi-party negotiation (one user + one counterparty per session).
- No real-world verification of facts (no scraping/OSINT).
- No self-hosted LLM infrastructure (external provider only).

## 2. Subscription tiers

### 2.1 Standard (default)
**Standard includes**
- Role play chat as the counterparty.
- Topic description (1–2 sentences) + minimal intake questions to configure the role play.
- Entity tray: attach existing entities from KG or create new.
- KG management: create/edit/delete entities and facts.
- Descriptive session recap (what happened) — **no advice**.

**Standard must NOT**
- Suggest what the user should say (“you should…”).
- Critique the user (“you conceded too early…”).
- Provide a negotiation strategy or recommended plan.
- Provide scenario trees or “next best move” guidance.

**Hard requirement:** Standard must never “accidentally coach” through roleplay outputs.

### 2.2 Premium
Premium adds (in separate UI channel from role play):
- Suggested replies (A/B/C) with intent labels.
- Strategy plan (anchor, concessions ladder, questions, red lines).
- Critique after user turns (clarity, concessions, info disclosure).
- Scenario tree (2–5 likely branches).
- After-action report (script v2 + optional follow-up message templates).
- Advanced epistemic controls (edit who knows what; confidence/source).

## 3. Core data concepts

### 3.1 Entities
An **Entity** is anything involved in the session:
- Person: user, friend, roommate, partner, parent, landlord/agent, recruiter/manager
- Organization: company, agency
- Artifact: offer, lease, contract, plan, agreement
- Place: property, flat, office (optional)
- Other: any user-defined entity type (allowed via custom entities)

### 3.2 Facts (atomic, reified)
A **Fact** is an atomic statement with provenance, e.g.:
- `Offer.base_salary = 50000 GBP`
- `Lease.end_date = 2026-02-11`
Facts must be:
- typed (value_type, unit)
- timestamped
- editable/deletable
- attributable to a source (user-entered, model-extracted, etc.)

### 3.3 Two-graph model
Maintain two related graphs:

1) **World Graph** (entities, relationships, facts)
- “What exists / what is true” (user-confirmed or user-entered).

2) **Epistemic Graph** (knowledge/visibility)
- “Who knows what”:
  - Employer typically knows salary, not rent.
  - Partner may know employer name, not office details.

The epistemic graph is the key constraint for realistic role play.

### 3.4 Sessions
A **Session** is a single role play chat:
- attaches a subset of KG entities (Entity Tray)
- has a topic/template
- stores chat messages
- stores session-only extracted facts until user confirms saving

## 4. Templates & topic understanding

### 4.1 Official template library (v0.1)
Ship with the following templates (interpersonal + everyday life):
1. Roommate conflict (chores/noise/guests/bills)
2. Relationship disagreement (boundaries/communication/priorities)
3. Dating / situationship (expectations/exclusivity/time)
4. Friendship conflict (respect/ghosting/loyalty)
5. Money with friends (owed money/splitting/trips)
6. Family / parental disagreement (independence/expectations/finances)
7. Workplace boundary / manager conflict (scope/feedback/recognition)
8. Salary offer / compensation negotiation
9. Rent / landlord / lease renewal
10. Refund / complaint dispute (consumer)

### 4.2 “Other” topic flow (required)
If topic doesn’t match official templates with sufficient confidence:
- use `template_id = other`
- run generic minimal intake (≤ 5 questions)
- start role play anyway
- trigger Template Agent to propose a draft template (local + review queue)

### 4.3 Template structure (requirements)
Each template must define:
- required entities/roles (User, Counterparty, optional third parties)
- slot schema (required + optional fields)
- question policy (minimal questions, skip logic, max questions target)
- role play parameters (default counterparty persona, typical objections)
- safety notes (if topic may intersect sensitive content)

### 4.4 Template Agent (draft template generation + patch proposals)
**Trigger A: unknown topic**
- router selects `other` → Template Agent generates a candidate template.

**Trigger B: template mismatch**
Even if an official template is selected, trigger Template Agent when:
- user adds “custom slots” repeatedly
- question optimizer cannot reach readiness without asking off-schema questions
- high edit/rejection rate suggests schema mismatch
- new entity types frequently appear for this template

**Template Agent output is a proposal, not an automatic change.**
- Proposal stored as `TemplateDraft` for that user (immediately usable for that user)
- Proposal queued for human review before becoming official

Human review is described in `docs/ADMIN_REVIEW.md`.

## 5. UX requirements

### 5.1 Design principle
- Chat-first; minimal screens.
- Memory is user-owned and visible; review-gated saving.

### 5.2 Screens
1) Home / Sessions list
2) New Session setup (3-step wizard max)
3) Session chat (main)
4) Memory manager (KG editor)
5) (Internal) Admin review tool

### 5.3 New Session setup wizard
**Step 1: Topic**
- Text or voice-to-text
- 1–2 sentence description

**Step 2: Entities**
- Show proposed entities as cards/chips
- Allow attach from memory (search)
- Allow create new (simple form)
- Allow edit/remove entities before starting

**Step 3: Minimal questions**
- Ask the minimum number of questions needed for roleplay realism
- Target ≤ 7 questions typical case
- Use skip logic based on earlier answers
- Start session

### 5.4 Session chat
Always:
- chat transcript
- composer
- entity tray (attached entities)
- counterparty style selector: Polite / Neutral / Tough / Busy / Defensive

Standard:
- role play only
- session recap allowed but descriptive only

Premium:
- coaching panel (separate channel)
- “What they know” editor

### 5.5 Memory review (end of session, required)
- List extracted facts discovered during session
- For each: Save globally / Save session-only / Discard
- Show provenance: “From message #N”
- Default: extracted facts are **session-only** until confirmed

### 5.6 Memory manager (KG)
- Search and browse entities
- Edit/delete entities and facts
- “Delete all memory” (hard delete + confirmation)
- Standard: view-only “What they know”
- Premium: edit epistemic edges

## 6. Role play requirements (Standard and Premium)

### 6.1 Counterparty simulator constraints
- Must stay in character as the counterparty.
- Must negotiate realistically with consistent persona.
- Must not access facts the counterparty does not know (epistemic filter).
- Must not output advice or critique (especially in Standard).

### 6.2 Counterparty style variants
User can select a style that affects tone and negotiation posture:
- Polite / Neutral / Tough / Busy / Defensive

### 6.3 “Replay variant” (optional in v0.1; recommended)
Allow rerunning the session setup with different counterparty style and the same entities.

## 7. Coaching requirements (Premium only)

### 7.1 Coach output channels
- Coach output must be separate from roleplay output.
- Coach must never speak “as the counterparty”.
- Coach can reference memory and epistemic model explicitly.

### 7.2 Coach features
- Suggested replies A/B/C (short, actionable, different styles)
- Strategy plan (anchor, concessions ladder, questions, red lines)
- Critique per turn (clarity, concessions timing, info leakage)
- Scenario tree (2–5 likely next branches)
- After-action report + script v2 + optional follow-up message

## 8. Knowledge Graph requirements (World graph)

### 8.1 Entities
- CRUD (create/edit/delete)
- User-owned (scoped per user)
- Support custom entity types (fallback “Custom”)

### 8.2 Facts
- Atomic, typed, timestamped
- Each fact must track provenance (see section 10)
- Facts can be global or session-only

### 8.3 Relationships
- Typed edges between entities (WORKS_AT, LIVES_WITH, DATES, PARENT_OF, RENTED_FROM, NEGOTIATING_WITH, etc.)
- Relationship creation can seed epistemic priors (see section 9)

## 9. Epistemic graph requirements (who knows what)

### 9.1 Knowledge edges
Represent `KNOWS(knower_entity -> fact)` with:
- status: confirmed / assumed / unknown / false_belief
- confidence: 0..1
- source: user_told / observed / inferred / public / third_party
- scope: global or session:<id>
- timestamps

### 9.2 Priors (relationship-based defaults)
When a relationship is created in the World graph, seed epistemic edges using priors:
- landlord knows rent and lease terms
- employer knows salary and job title
- roommate knows shared bills
- partner may know employer name (if user chooses to store it)
Priors must never override user edits.

### 9.3 Disclosure rules during chat
- If user says a fact in the roleplay chat, the counterparty gains knowledge of that fact for this session scope.
- If user says a fact only to the Premium coach, counterparty does NOT gain knowledge.

## 10. Provenance & telemetry (training-ready)

### 10.1 Fact provenance (required)
Every fact must have:
- source_type: user_entered | user_confirmed_extraction | model_extracted | inferred | external
- source_ref: session_id, message_id, ui_form_id, etc.
- model_version / prompt_version when relevant
- confidence
- timestamps

### 10.2 Event sourcing (required)
All edits to entities/facts/knowledge edges must emit immutable events (see `docs/EVENTS.md`).

### 10.3 Consent & privacy controls (required)
Provide separate opt-ins:
1) Save to personal memory (KG)
2) Share anonymized telemetry to improve app
3) Share raw conversation text for training (explicit, highest sensitivity)

### 10.4 Deletion propagation (required)
Deleting facts/entities must propagate to:
- KG tables
- derived stores (embeddings/caches if added later)
- training dataset builder (via tombstones)

## 11. External LLM provider requirement

### 11.1 Provider-agnostic LLM gateway
- The backend must call an external LLM provider via a gateway interface:
  - streaming support
  - retries
  - timeouts
  - cost/usage accounting hooks

### 11.2 No self-hosting assumption
- No vLLM/llama.cpp deployment requirements in v0.1.

## 12. Acceptance criteria (v0.1 MVP)

### Standard
- Start session with 1–2 sentence topic, attach entities, answer minimal questions, enter roleplay chat.
- Counterparty roleplay is consistent and respects epistemic knowledge.
- No coaching language in Standard outputs.
- User can reuse entities across sessions.
- End-session memory review saves/keeps/discards extracted facts.

### Premium
- Coaching panel provides suggestions and critique separate from roleplay.
- Disclosure tracking (chat vs coach) works.
- Suggestion “used” events logged.

### Template evolution
- `other` triggers draft template generation and review queue entry.
- Template patch proposals generated when mismatch signals occur.
