# NeGot Prototype Spec (Minimal Roleplay)

This prototype is intentionally minimal and domain-agnostic. It runs a single simulation with multi-round roleplay where:
- UserProxy argues for the USER's desired outcome from the UI.
- Counterparty responds realistically given the environment assumptions.
- Each agent receives the full message history embedded in the composed system prompt.

## Core Flow

1. Create a CaseSnapshot.
2. Run simulations (multi-round, max set by user):
   - Turn 1: USER (UserProxy)
   - Turn 2: COUNTERPARTY
3. After each round (USER + COUNTERPARTY), WorldAgent evaluates PASS / NEUTRAL / FAIL.
4. Persist run + trace.

Notes:
- Runs are executed concurrently (async) with a configurable limit (`MAX_PARALLEL_RUNS`).

## Issues (per-party)

- Agents receive issues from their own perspective (`user_issues` for UserProxy, `counterparty_issues` for Counterparty).
- If per-party lists are not provided, the shared `issues` list is used as a fallback.

## Outcomes (user perspective)

- PASS: counterparty offer meets or exceeds the user's target (direction-aware).
- NEUTRAL: counterparty offer is between reservation and target (direction-aware).
- FAIL: counterparty offer is worse than reservation or no clear offer.

## Strategy Suggestions

- Sample 4 strategies from the registry each run.
- Provide them as optional suggestions to both agents.
- Agents may use them or ignore them; usage is recorded in `used_strategies`.

## Prompt Output (both agents)

```json
{
  "action": { "type": "ASK_INFO|PROPOSE_OFFER|COUNTER_OFFER|ACCEPT|REJECT|CONCEDE|TRADE|PROPOSE_PACKAGE|REQUEST_CRITERIA|SUMMARIZE_VALIDATE|DEFER_AND_SCHEDULE|ESCALATE_TO_DECIDER|WALK_AWAY|TIMEOUT_END", "payload": {} },
  "message_text": "string",
  "used_strategies": ["STRAT_ID"]
}
```

## Prompt Payload

- Each agent call sends:
  - A **system** message containing the prompt content before the `<<PROMPT_SPLIT>>` token.
  - A **user** message containing everything after the `<<PROMPT_SPLIT>>` token, plus the formatted conversation history (USER/COUNTERPARTY/WORLDAGENT).

## Trace (minimal)

- Per run: seed + strategy suggestions + extracted structure (offers, concessions, packages, asks, objections, arguments).
- Per run: run summary (summary + key_points).
- Per turn: speaker, message_text, conversation so far, outcome.
- Per agent call: prompt (system + formatted history) + raw/parsed output.

## Future Work

- Support dynamic per-turn clarification injection for long-running/parallel simulations (refresh Q&A mid-run).
