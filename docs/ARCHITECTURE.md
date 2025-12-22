# Architecture (v0.1)

This doc describes a minimal architecture that satisfies `docs/REQUIREMENTS.md`.

## 1. High-level components

### 1.1 Frontend
- Chat-first web app UI:
  - sessions list
  - new session wizard (topic → entities → minimal questions)
  - chat session (roleplay)
  - memory manager (KG CRUD)
  - premium coaching panel (gated)
  - web grounding indicator + citations panel (when used)

### 1.2 Backend services (logical)
1) **API Gateway** (HTTP + streaming)
2) **Session Service** (messages, session metadata)
3) **Template Service** (official templates, draft templates, proposals)
4) **KG Service** (World graph CRUD)
5) **Visibility Service** (priors + disclosure tracker + user overrides)
6) **Web Grounding Service** (NeedSearch → query planning → Tavily → synthesis)
7) **LLM Orchestrator** (LangGraph state graph for roleplay + coaching; Instructor for extraction)
8) **Events Service** (append-only log)
9) **Observability** (Langfuse traces + prompt/version tracking)
10) **Auth/Tier Gate** (standard vs premium)

Implementation may begin as a monolith, but keep internal module boundaries.

## 2. Orchestration as a state machine / graph

### 2.1 Session start flow
1) TopicRouter → template_id (or `other`)
2) EntityProposer (suggest entities/roles)
3) QuestionPlanner (minimal questions; skip logic)
4) SetupComplete → session starts

### 2.2 Per-turn flow
Input: user message `m_t`

1) Persist message
2) Extract candidates (facts + entity updates; session-only)
3) Disclosure update (counterparty learned facts in this session scope)
4) Retrieve context:
   - attached entities only
   - 1–2 hop subgraph
   - template-filtered + recency-weighted
5) Web grounding (optional):
   - NeedSearch gate decides if web grounding is required
   - if yes, run Web Grounding Service and attach Grounding Pack
6) Visibility filter:
   - compute visible facts for counterparty (priors + disclosures + overrides)
7) LangGraph orchestrator builds prompt context (system + history + visible facts)
8) Roleplay generation (counterparty message)
9) Premium only:
   - Coach generation (separate channel)
10) Emit events for each step (including ORCHESTRATION_CONTEXT_BUILT with prompt messages)

### 2.2.1 LangGraph nodes (v0.1)
- build_prompt: assemble system instructions + history + visible facts.
- roleplay: call LiteLLM unless streaming (streaming builds prompt only).
- coach: premium-only coaching output (separate channel).

### Context payload contract (must make unknowns explicit)
Even if the DB stores epistemic knowledge sparsely (absence means unknown), the orchestrator must create a context payload including:
- `visible_facts` for counterparty
- `prompt_messages` (system + recent history + current user message)
- `unknown_required_slots` (still missing)
- `grounding_pack` (optional, with citations)
- `unknown_by_design_note` reminding that missing data is unknown and must not be assumed

Hard rule: roleplay may only reference `visible_facts` + grounded web context; everything else is unknown.

### 2.3 Session end flow
1) Recap:
   - Standard: descriptive only
   - Premium: after-action report
2) Memory review gating (user choices)
3) Commit approved facts to global KG via events

## 3. Web grounding (Tavily) in-process module
For v0.1, web grounding is implemented as an in-repo module, not a separate service.
Keep it behind a clean interface so it can be split later if needed.

Core functions:
- `need_search(context) -> decision`
- `plan_queries(context, decision) -> queries`
- `tavily_search(queries, params) -> results`
- `synthesize(results, context) -> grounding_pack`

Caching:
- query-level cache (normalized query + region) with TTL
- session-level cache (reuse within session)

## 4. Deterministic replay (recommended)
To replay a session deterministically, store:
- orchestration version
- prompt templates + versions
- LLM model identifiers
- the retrieved context payload (including grounding pack)
- decoding params

## 5. Guardrails for Standard vs Premium
- Standard code path must never call coaching nodes.
- Roleplay prompts forbid advice/critique.
- Add a post-generation “no-coaching” + “no invented facts” validator for Standard.

See `docs/SAFETY.md`.
