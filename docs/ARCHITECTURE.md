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
5) **Visibility Service** (LLM selection using knowledge edges + disclosures)
6) **Web Grounding Service** (LLM NeedSearch -> LLM query planning -> Tavily -> LLM synthesis)
7) **LLM Orchestrator** (LangGraph state graph for roleplay + coaching; Instructor for extraction)
8) **Strategy Pack Service** (load/validate packs, strategies, rubrics)
9) **Case Snapshot Service** (structured negotiation state)
10) **Strategy Selection Service** (LLM ranks strategies from snapshot)
11) **Strategy Execution Service** (artifacts + rubric critiques + JSON patches)
12) **Events Service** (append-only log)
13) **Observability** (Langfuse traces + prompt/version tracking)
14) **Auth/Tier Gate** (standard vs premium)

Implementation may begin as a monolith, but keep internal module boundaries.

## 2. Orchestration as a state machine / graph

### 2.1 Session start flow
1) TopicRouter (LLM) -> template_id (or `other`)
2) EntityProposer (LLM) (suggest entities/roles)
3) CaseSnapshot init (domain/channel/stage/default issue)
4) QuestionPlanner (LLM) (minimal questions; includes strategy-signal questions)
5) Intake submission updates CaseSnapshot (LLM JSON patches)
6) StrategySelection (LLM) -> ranked strategies
7) SetupComplete -> session starts
### 2.2 Per-turn flow
Input: user message `m_t`

1) Persist message
2) Update CaseSnapshot (LLM JSON patches + timeline append)
3) Load selected strategy context (from intake selection; no per-turn refresh)
4) Extract candidates (facts + entity updates; session-only; LLM extraction)
5) Disclosure update (counterparty learned facts in this session scope)
6) Retrieve context:
   - attached entities only
   - 1-2 hop subgraph
   - template-filtered + recency-weighted
7) Web grounding (optional):
   - LLM NeedSearch decides if web grounding is required
   - if yes, run Web Grounding Service and attach Grounding Pack
8) Visibility filter:
   - LLM selects visible facts using knowledge edges + disclosures
9) LangGraph orchestrator builds prompt context (system + history + visible facts + selected strategy)
10) Roleplay generation (counterparty message)
11) Premium only:
   - Coach generation (separate channel)
12) Emit events for each step (including ORCHESTRATION_CONTEXT_BUILT with prompt messages)

### 2.2.1 LangGraph nodes (v0.1)
LangGraph is mandatory for roleplay + coaching orchestration in all tiers.
There is no non-graph fallback; if LangGraph is unavailable, the service should fail fast.

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

### 2.2.2 Strategy execution (user-triggered)
1) User runs selected strategy (no manual strategy picking required)
2) StrategyExecutor generates artifacts + judge outputs
3) Apply case patches (preview if UI supports)
4) Persist StrategyExecution + artifacts + events
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
- `need_search(context) -> decision` (LLM) (LLM)
- `plan_queries(context, decision) -> queries` (LLM) (LLM)
- `tavily_search(queries, params) -> results`
- `synthesize(results, context) -> grounding_pack` (LLM) (LLM)

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
## 6. Strategy system integration plan
- Load and validate strategy packs at startup (schemas + manifests).
- Maintain a CaseSnapshot per session (intake + message updates via JSON patch).
- Run LLM-based strategy selection once after intake; reuse per turn.
- Inject selected strategy context into roleplay prompts (no user-facing reveal).
- Provide strategy controls embedded in the chat experience for execution/artifacts.
- Persist StrategySelection and StrategyExecution outputs with events.

