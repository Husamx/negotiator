# Web Grounding (v0.1) — Tavily search RAG

This module provides “internet-search RAG” to support topics requiring common knowledge:
culture/norms/etiquette, public policy, common practices, or time-sensitive facts.

## 1. Design goals
- Invoke web search **only when needed** (cost control).
- Produce a compact **Grounding Pack** with **citations**.
- Enforce: **unknown stays unknown** (no invented facts).
- Integrate in-process in the app (not a separate project in v0.1).

## 2. Pipeline (planner → search → interpreter)

### 2.1 NeedSearch Gate (LLM, strict schema)
Inputs:
- topic description (1–2 sentences)
- template_id
- region hints (country/city if provided)
- user question (if mid-chat)
- known facts + unknown required slots

Outputs (JSON):
```json
{
  "need_search": true,
  "reason_codes": ["CULTURE_NORMS"],
  "max_queries": 2,
  "max_sources_per_query": 5,
  "search_depth": "basic",
  "topic": "general"
}
```

Trigger examples (used as guidance for the agent):
- culture/norms (“in Japan”, “custom”, “etiquette”, “norms”)
- policy/legal (“is it legal”, “tenant rights”, “notice period”)
- time-sensitive (“current”, “latest”, “typical market”, “2025”)
- niche institutions/laws/policies (named bills, official policies)

The agent always returns a strict JSON decision.

### 2.2 QueryPlanner (LLM, budgeted)
- max 1–3 queries
- include region if available
- include stop conditions (e.g., “2 reputable sources agree”)

Output (JSON):
```json
{
  "queries": ["...","..."],
  "must_have_evidence": ["..."],
  "stop_conditions": ["..."]
}
```

### 2.3 Tavily Search
Call Tavily with the tavily-python SDK (fallback to direct HTTP when needed), using:
- `search_depth`: default `basic`
- `max_results`: default 5
- `topic`: general/news/finance (default general)
- `include_answer`: false (default)
- `include_raw_content`: false (default; enable only if necessary)

### 2.4 EvidenceSynthesizer (LLM, structured)
Transforms results into a **Grounding Pack**:

```json
{
  "key_points": [
    {"text": "...", "sources": [{"url":"...","title":"..."}], "confidence": 0.8}
  ],
  "norms_and_expectations": [...],
  "constraints_and_rules": [...],
  "disputed_or_uncertain": [...],
  "what_to_ask_user": [
    {"q":"...", "why":"..."}
  ]
}
```

Hard rules:
- Every non-trivial claim must have citations OR be placed under `disputed_or_uncertain` / labeled unknown.
- Do not infer personal facts about the user.
- Prefer multiple sources for policy/legal-like constraints.

## 3. Cost control & caching (hard requirements)
- Default session budgets:
  - Standard: max 2 searches/session; max 1 mid-chat search unless user asks.
  - Premium: max 4 searches/session.
- Cache:
  - query cache: normalized_query + region → results (TTL 24–72h)
  - session cache: reuse grounding pack within session
- Force `search_depth="basic"` unless explicitly needed.

## 4. Integration points
- Session setup: after minimal questions, if NeedSearch true → run grounding once.
- Mid-chat: run grounding only if user asks for external facts OR realism is blocked.
- Roleplay uses grounding pack as *background realism* only (Standard must not coach).
- Premium coach can reference grounding pack with citations.

## 5. Events (see docs/legacy/EVENTS.md)
Emit:
- WEB_GROUNDING_DECIDED
- WEB_GROUNDING_QUERY_PLANNED
- WEB_GROUNDING_CALLED
- WEB_GROUNDING_PACK_CREATED
- WEB_GROUNDING_SHOWN_TO_USER

## 6. Safety notes
- Do not present legal advice as definitive; present as “based on sources” and encourage professional advice when appropriate.
- Respect user consent for storing raw content.
