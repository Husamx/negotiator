# Requirements (v0.1)

> This document is the **source of truth** for what the app must do in v0.1.

## 1. Product scope

### 1.1 Goal
Build a chat-based rehearsal app where:
- Every negotiation is a **chat session** (“role play”).
- Users can **reuse entities** (people, places, organizations, offers, leases, etc.) across sessions via a persistent **Knowledge Graph (KG)**.
- The role play stays realistic by modeling **who knows what** (visibility / epistemic constraints).
- **Standard** is role play only; **Premium** adds coaching.
- The app can use **web grounding** (internet search RAG) when topic realism requires common knowledge (culture/norms/policy).

### 1.2 Target audience (v0.1)
- People in their twenties.
- Primary templates: interpersonal disagreements + everyday life negotiations.

### 1.3 Non-goals (v0.1)
- No automated outreach (sending emails/SMS in-app).
- No multi-party negotiation (one user + one counterparty per session).
- No real-world verification of personal facts (no OSINT).
- No self-hosted LLM infrastructure (external provider only).
- No full “graph visualization” UI.

## 2. Subscription tiers

### 2.1 Standard (default)
Standard includes:
- Role play chat as the counterparty.
- Topic description (1–2 sentences) + minimal intake questions.
- Entity tray: attach existing entities from KG or create new.
- KG management: create/edit/delete entities and facts.
- Web grounding (Tavily) only when required (see section 12).
- Descriptive session recap (what happened) — **no advice**.

Standard must NOT:
- Suggest what the user should say (“you should…”).
- Critique the user (“you conceded too early…”).
- Provide a negotiation strategy plan.
- Provide “next best move” guidance.

Hard requirement: Standard must never “accidentally coach” through roleplay outputs.

### 2.2 Premium
Premium adds (separate UI channel from role play):
- Suggested replies (A/B/C) with intent labels.
- Strategy plan (anchor, concessions ladder, questions, red lines).
- Critique after user turns (clarity, concessions, info disclosure).
- Scenario tree (2–5 likely branches).
- After-action report (script v2 + optional follow-up message templates).
- Advanced visibility controls (edit what the counterparty knows; confidence/source).

## 3. Core data concepts

### 3.1 Entities
An **Entity** is anything involved in the session:
- Person: user, friend, roommate, partner, parent, landlord/agent, recruiter/manager
- Organization: company, agency
- Artifact: offer, lease, contract, plan, agreement
- Place: property, flat, office (optional)
- Other: any user-defined entity type

### 3.2 Facts (atomic, reified)
A **Fact** is an atomic statement with provenance, e.g.:
- `Offer.base_salary = 125000 GBP`
- `Lease.end_date = 2026-02-11`
Facts must be typed, timestamped, editable/deletable, and attributable to a source.

### 3.3 Two-graph model (world + epistemic)
Maintain two related graphs:

1) **World Graph**: entities, relationships, facts (“what exists / is true”)
2) **Visibility/Epistemic Model**: who knows what (“what the counterparty can use”)

v0.1 implementation: **sparse** epistemic storage + **runtime priors + disclosure tracker**.
- Do NOT store unknown edges exhaustively.
- Absence of an edge means **UNKNOWN**.

### 3.4 Sessions
A **Session** is a single role play chat:
- attaches a subset of KG entities (Entity Tray)
- has a topic/template
- stores messages
- stores extracted facts as session-only candidates until user confirms saving

## 4. Templates & topic understanding

### 4.1 Official template library (v0.1)
Ship with:
1. Roommate conflict
2. Relationship disagreement
3. Dating / situationship expectations
4. Friendship conflict
5. Money with friends
6. Family / parental disagreement
7. Workplace boundary / manager conflict
8. Salary offer / compensation negotiation
9. Rent / landlord / lease renewal
10. Refund / complaint dispute

### 4.2 “Other” topic flow
If topic doesn’t match official templates with sufficient confidence:
- use `template_id = other`
- run generic minimal intake (≤ 5 questions)
- start role play anyway
- trigger Template Agent to propose a draft template (local + review queue)

### 4.3 Template structure (requirements)
Each template defines:
- required entities/roles (User, Counterparty, optional third parties)
- slot schema (required + optional fields)
- question policy (minimal questions, skip logic, max questions target)
- role play parameters (default persona, typical objections)
- safety notes

### 4.4 Template Agent
Triggers:
- Unknown topic (`other`) → generate a user-local TemplateDraft + TemplateProposal.
- Mismatch signals (custom slots, repeated edits, low realism ratings) → propose a patch.

TemplateDraft: usable immediately for that user, marked `draft=true`.
TemplateProposal: queued for human review before becoming official.

## 5. UX requirements

### 5.1 Design
- Chat-first; minimal screens.
- Memory is user-owned and review-gated.
- Web grounding is transparent: show citations and what was retrieved.

### 5.2 Screens
1) Home / Sessions list
2) New Session setup (3-step wizard max)
3) Session chat (main)
4) Memory manager (KG editor)
5) (Internal) Admin review tool

### 5.3 New Session wizard
Step 1: Topic (text or voice-to-text; 1–2 sentences)
Step 2: Entities (attach existing or create new)
Step 3: Minimal questions (≤ 7 typical; skip logic)

### 5.4 Session chat
Always:
- transcript + composer
- entity tray (attached entities)
- counterparty style selector: Polite / Neutral / Tough / Busy / Defensive

Standard:
- role play only
- descriptive recap allowed (no advice)

Premium:
- coaching panel
- visibility editor (“what they know”)

### 5.5 Memory review (end of session)
- List extracted facts discovered during session
- For each: Save globally / Save session-only / Discard
- Show provenance: “From message #N”
- Default: extracted facts are **session-only** until confirmed

## 6. Role play requirements

### 6.1 Counterparty simulator constraints
- Stay in character as counterparty; consistent persona.
- Respect visibility: must not access facts counterparty does not know.
- Must not output advice/critique (especially Standard).

### 6.2 Style variants
- Polite / Neutral / Tough / Busy / Defensive

## 7. Coaching requirements (Premium only)
Separate channel from role play:
- suggested replies A/B/C
- strategy plan
- critique per turn
- scenario branches (2–5)
- after-action report

## 8. Knowledge Graph (World graph)

### 8.1 Entities
CRUD, user-owned, custom entity types allowed.

### 8.2 Facts
Atomic, typed, timestamped, provenance-tracked.
Scope: global or session-only.

### 8.3 Relationships
Typed edges (WORKS_AT, LIVES_WITH, DATES, PARENT_OF, RENTED_FROM, etc.)

## 9. Visibility/Epistemic model (“who knows what”)

### 9.1 Sparse storage rule
Do NOT store explicit `unknown` edges for all (entity × fact). Absence means UNKNOWN.

Store knowledge edges only for:
- confirmed knowledge (disclosed in chat)
- user overrides (explicitly set)
- optional false beliefs (future)

### 9.2 Priors (relationship-based defaults)
When a relationship is created, seed *priors* (rules) for what categories are likely known.
Priors affect **visibility only** and must never invent missing values.

### 9.3 Disclosure rules
- If the user states a fact in roleplay chat, the counterparty gains knowledge of that fact (session scope).
- If user states it only to Premium coach, counterparty does NOT gain knowledge.

### 9.4 Unknown must remain unknown (hard requirement)
- Agents must not assume missing values or private facts.
- Orchestrator must include explicit `unknown_required_slots` and/or `unknown_by_design_note` in LLM context.
- If unknown blocks realism, ask a clarifying question (in-character for roleplay) or branch with labeled assumptions (Premium only).

## 10. Provenance & telemetry (training-ready)

### 10.1 Fact provenance
Every fact must have:
- source_type: user_entered | user_confirmed_extraction | model_extracted | inferred | external
- source_ref: session_id/message_id/ui_form_id/etc.
- model_version / prompt_version when relevant
- confidence, timestamps

### 10.2 Event sourcing
All edits to entities/facts/knowledge edges emit immutable events (`docs/EVENTS.md`).

### 10.3 Consent & privacy controls
Separate opt-ins:
1) Save to personal memory (KG)
2) Share anonymized telemetry
3) Share raw conversation text (explicit)

### 10.4 Deletion propagation
Deleting facts/entities must propagate to derived stores (embeddings/caches later) via tombstones.

## 11. External LLM provider
- Must call an external LLM provider via a provider-agnostic gateway:
  - streaming support
  - retries/timeouts
  - usage accounting hooks
- No self-hosting assumptions in v0.1.

## 12. Web grounding (internet search RAG) — Tavily

### 12.1 Why
If the user’s topic requires common knowledge from the internet (culture/norms/etiquette/policy/common practices),
the app should fetch grounded context to avoid interrogating the user for every detail.

### 12.2 Provider
Use **Tavily** Search API in v0.1.

### 12.3 Cost control (hard requirements)
- Do not search unless needed.
- Default budget:
  - Standard: max 2 searches per session (typical); max 1 mid-chat search unless user asks.
  - Premium: max 4 searches per session.
- Default parameters:
  - search_depth = basic (avoid advanced unless explicitly needed)
  - max_results = 5
- Cache search results by normalized query + region with TTL (24–72h).

### 12.4 Search agent responsibilities
Implement a small web-grounding pipeline:
1) NeedSearch Gate (LLM, strict schema)
2) QueryPlanner (LLM, max 1–3 queries)
3) Tavily Search
4) EvidenceSynthesizer (LLM) → Grounding Pack (bullets with citations, plus “uncertain/disputed”)

Hard rule: Do not invent facts; everything in the Grounding Pack must cite retrieved sources or be labeled unknown.

### 12.5 UX requirements
- When web grounding is used, surface:
  - “Used web sources” indicator
  - bullet summary with citations
  - what questions remain unanswered (unknowns)

See `docs/WEB_GROUNDING.md` for schemas and endpoints.

## 13. Acceptance criteria (v0.1 MVP)

Standard:
- Create session from 1–2 sentence topic, attach entities, answer minimal questions, start roleplay.
- Counterparty respects visibility; no coaching language.
- Web grounding is only invoked when needed; citations shown when used.
- Memory review saves/keeps/discards extracted facts.

Premium:
- Coaching panel provides suggestions/critique separate from roleplay.
- Disclosure tracking works (chat vs coach).
- Web grounding can feed coaching with citations.

Template evolution:
- `other` triggers draft template generation + review queue entry.
