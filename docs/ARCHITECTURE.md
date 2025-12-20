# Architecture (v0.1)

This doc describes the proposed architecture that satisfies `docs/REQUIREMENTS.md`.

## 1. High-level components

### 1.1 Frontend
- Web app (recommended for v0.1) with a chat-first UI:
  - sessions list
  - new session wizard (topic → entities → minimal questions)
  - chat session screen (roleplay)
  - memory manager (KG CRUD)
  - premium coaching panel (feature gated)

### 1.2 Backend services (logical)
1) **API Gateway** (HTTP + streaming)
2) **Session Service** (messages, session metadata)
3) **Template Service** (official templates, draft templates, proposals)
4) **KG Service** (World graph CRUD)
5) **Epistemic Service** (knowledge edges, priors, disclosure updates)
6) **LLM Orchestrator** (roleplay, extraction; coaching for premium)
7) **Events Service** (append-only event log + analytics hooks)
8) **Auth/Billing** (tier gating)

Implementation may be a single backend app initially, but internal boundaries must match the above.

## 2. Orchestration as a state machine

### 2.1 Session start flow
1) TopicRouter: classify topic → template_id (or `other`)
2) EntityProposer: propose entities/roles based on template
3) QuestionPlanner: generate minimal questions (skip logic)
4) SetupComplete: session starts

### 2.2 Per-turn flow
Input: user message `m_t`

1) **Persist message**
2) **Extract candidates** (facts + entity updates; session-only)
3) **Disclosure update** (epistemic edges for counterparty in this session scope)
4) **Retrieve context**:
   - attached entities only
   - 1–2 hop subgraph
   - template/topic-filtered
   - recency weighted
5) **Epistemic filter**: restrict facts visible to counterparty
6) **Roleplay generate**: produce counterparty message
7) **Premium only**:
   - Coach generate (suggestions, critique, scenarios)
8) **Emit events** for each step

### 2.3 Session end flow
1) Generate recap:
   - Standard: descriptive only
   - Premium: after-action report
2) Memory review gating (user choices)
3) Commit approved facts to global KG (via events)

## 3. Deterministic replay
To replay a session deterministically, store:
- orchestration version
- prompt templates + versions
- LLM model identifiers
- the exact retrieved context payload
- random seeds if any sampling is used (or configure deterministic decoding)

## 4. External LLM gateway interface
The orchestrator must call a provider-agnostic LLM interface:
- `generate(messages, tools?, json_schema?, stream?)`
- `stream_generate(...)`
- return usage accounting metadata

See `docs/API.md` and `docs/DATA_MODEL.md` for recommended fields to store.

## 5. Guardrails for Standard vs Premium
- Standard code path must never call coaching nodes.
- Roleplay prompts must forbid advice/critique.
- Add a post-generation “no-coaching” filter for Standard that detects banned patterns and regenerates.

See `docs/SAFETY.md`.
