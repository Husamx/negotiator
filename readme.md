# Negotiation Companion (working name)

A chat-based rehearsal app to help people **practice** negotiations, debates, and difficult conversations before having them — initially tailored to people in their twenties.

This repo currently contains the **v0.1 specifications + system design** (Markdown docs) and an initial **Python/Poetry dependency spec**. Implementation can be built directly from these docs.

---

## What the app does

### Modes (tiers)
- **Standard (default):** *role play only* (the app plays the counterparty).  
  No advice, no critique, no “what you should say.”
- **Premium:** role play **plus coaching** (suggested replies, strategy, critique, scenario branches, after-action report).

### Key product ideas
- **Chat-first:** every negotiation is a chat session.
- **User-owned memory:** a persistent **Knowledge Graph (KG)** stores entities and facts that users can reuse across sessions.
- **Realistic role play:** counterparty responses are constrained by **what they know** (“visibility / epistemics”).
- **Web grounding when needed:** if the topic requires common knowledge (culture/norms/policy/common practices), the system can run **internet search RAG** (Tavily) and present **citations** — but only when it’s worth the cost.

---

## Non-negotiable constraints (must be enforced)

1. **No coaching in Standard**
   - Standard must not output advice, critique, or suggested replies.
2. **Unknown must remain unknown**
   - Missing info is treated as **UNKNOWN**; agents must not assume or invent values.
3. **Counterparty visibility**
   - The roleplay agent can only use facts the counterparty is allowed to know.
4. **Memory is review-gated**
   - Extracted facts are “session-only candidates” until the user confirms what to save.
5. **Web grounding is gated + cited**
   - Only run search when needed; when used, show citations and highlight uncertainty.

These are enforced through prompt policies + orchestration rules + post-generation validators (see `docs/SAFETY.md`).

---

## Core concepts (domain model)

- **Session:** one rehearsal chat (topic + template + messages + attached entities).
- **Entity:** people/organizations/artifacts/places involved (e.g., landlord, partner, offer, lease).
- **Fact (atomic):** a typed statement about an entity with provenance (e.g., `Offer.base_salary = 125000 GBP`).
- **World graph:** entities + relationships + facts (“what exists / is true”).
- **Visibility / Epistemics:** who knows which facts (“what the counterparty can use”).
  - v0.1 uses **sparse storage + runtime priors + disclosure tracking** (absence implies unknown).
- **Template:** a topic schema (required slots + minimal questions + roleplay parameters).
- **Grounding Pack:** web-sourced context (bullets with citations + uncertainty + follow-up questions).

---

## Main workflows

### 1) New session setup (3-step max)
1. **Topic**: user writes 1–2 sentences (or voice-to-text).
2. **Entities**: attach existing entities from KG or create new ones.
3. **Minimal questions**: template-driven questions (aim ≤ 7 typical) to fill only what matters.

### 2) Per-turn chat loop (high-level)
For each user message:

1. Persist user message  
2. Extract candidate facts/entities (session-only; not committed)  
3. Update **disclosure** (facts revealed in roleplay chat become known to counterparty for this session)  
4. Retrieve relevant KG context (attached entities + small subgraph)  
5. **Web grounding (optional)**  
   - NeedSearch gate → Query planning → Tavily search → Evidence synthesis → Grounding Pack  
6. Compute **visible facts** for the counterparty (priors + disclosures + overrides)  
7. Generate counterparty roleplay response (Standard path)  
8. Premium-only: generate coaching output in a separate channel  
9. Emit events for analytics/training (with consent)

### 3) End session memory review
- Show extracted fact candidates with provenance
- User decides: **Save globally / Save session-only / Discard**
- Apply deletion/editing with tombstones and event sourcing

---

## Web grounding (internet-search RAG) at a glance

The app can fetch common knowledge when required (culture/norms/etiquette/policy/common practices).

- **Planner:** decides if search is needed (cost-effective gating)
- **Search:** runs Tavily (budgeted)
- **Interpreter:** synthesizes a **Grounding Pack** with citations and uncertainty

Hard rules:
- Do not search unless needed.
- Do not invent facts; every non-trivial grounded claim must cite sources.

Details: `docs/WEB_GROUNDING.md`

---

## Where to read details (recommended order)

If you’re implementing the codebase, read in this order:

1. **`README.md`** (this file) — the big picture + invariants  
2. **`docs/REQUIREMENTS.md`** — source of truth for features and constraints  
3. **`docs/ARCHITECTURE.md`** — modules + orchestration flows + context payload contract  
4. **`docs/DATA_MODEL.md`** — tables for sessions, KG, epistemics, grounding, events  
5. **`docs/API.md`** — endpoints + streaming + tier gating  
6. **`docs/SAFETY.md`** — guardrails + “unknown stays unknown” + Standard no-coaching validator  
7. **`docs/WEB_GROUNDING.md`** — Tavily pipeline + budgets + schemas  
8. **`docs/TEMPLATES.md`** + **`docs/ADMIN_REVIEW.md`** — template library + draft/review workflow  
9. **`docs/EVENTS.md`** — telemetry/event taxonomy (consent-aware)

---

## Implementation order (suggested build plan)

1. **DB schema + migrations** (sessions/messages/entities/facts/relationships/events)
2. **Session API skeleton** (create session, post message, end session)
3. **Roleplay loop (Standard)** with visibility filtering (no coaching)
4. **Memory review gating** (extract → confirm → commit)
5. **Web grounding module** (NeedSearch → plan → Tavily → synthesize) + caching + UI surfacing
6. **Premium coaching path** (separate channel + strict gating)
7. **Template draft/proposal workflow** + internal admin tool

---

## Repo map

- `docs/REQUIREMENTS.md` — product requirements (v0.1)
- `docs/ARCHITECTURE.md` — system design + orchestration
- `docs/DATA_MODEL.md` — KG + epistemics + grounding + event sourcing
- `docs/WEB_GROUNDING.md` — Tavily search RAG design
- `docs/API.md` — API contract outline
- `docs/SAFETY.md` — safety + Standard vs Premium guardrails
- `docs/TEMPLATES.md` — templates + “Other” + draft workflow
- `docs/ADMIN_REVIEW.md` — human review process for templates
- `docs/EVENTS.md` — telemetry & training signals
- `docs/DEPENDENCIES.md` — package choices + licensing notes
- `docs/SETUP.md` — developer setup
- `pyproject.toml` — Poetry dependencies/groups
- `.env.example` — environment variable template

---

## Setup

See `docs/SETUP.md`.
