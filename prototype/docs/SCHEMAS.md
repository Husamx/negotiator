# Schemas (Minimal Roleplay)

Canonical definitions live in `prototype/src/backend/app/core/models.py`.
This file summarizes the minimal runtime shapes used by the current engine.
See `docs/AGENTS.md` for agent roles and prompt ownership.

## CaseSnapshot (summary)

```json
{
  "case_id": "uuid",
  "revision": 1,
  "created_at": "iso",
  "status": "DRAFT|READY|SIMULATED",
  "topic": "string",
  "domain": "GENERAL|JOB_OFFER_COMP|RENT_HOUSING|PROCUREMENT_VENDOR|SERVICES_CONTRACTOR",
  "channel": "UNSPECIFIED|IN_PERSON|EMAIL|DM",
  "parameters": [
    {
      "param_id": "string",
      "label": "string",
      "value_type": "MONEY|NUMBER|TEXT|DATE|ENUM|BOOLEAN",
      "value": "any",
      "class": "NON_NEGOTIABLE|HARD_IN_RUN_REVISABLE|PREFERENCE",
      "disclosure": "PRIVATE|SHAREABLE|CONDITIONAL",
      "applies_to": { "scope": "OFFER|DISCLOSURE|SCHEDULE|OTHER", "issue_id": "optional" }
    }
  ],
  "objectives": {
    "target": { "type": "OFFER_VECTOR|SINGLE_VALUE", "value": "any" },
    "reservation": { "type": "OFFER_VECTOR|SINGLE_VALUE", "value": "any" },
    "no_deal_acceptable": false,
    "issue_weights": { "issue_id": 1.0 }
  },
  "issues": [
    {
      "issue_id": "string",
      "name": "string",
      "type": "PRICE|SALARY|DATE|SCOPE|RISK|BENEFIT|OTHER",
      "direction": "MINIMIZE|MAXIMIZE",
      "unit": "GBP|USD|days|text",
      "bounds": { "min": "optional", "max": "optional" }
    }
  ],
  "user_issues": [ "... optional per-user issue list ..." ],
  "counterparty_issues": [ "... optional per-counterparty issue list ..." ],
  "counterparty_assumptions": {
    "calibration": { "answers": {} },
    "persona_distribution": [{ "persona_id": "GENERIC", "weight": 1.0 }],
    "notes": "optional"
  },
  "clarifications": [
    { "question": "string", "answer": "any" }
  ],
  "controls": { "... sliders ..." },
  "mode": { "auto_enabled": true, "advanced_enabled": true, "enabled_strategies": [], "pinned_strategy": null }
}
```

Notes:
- `issues` is optional when both `user_issues` and `counterparty_issues` are provided. Shared `issues` acts as a fallback when per-party lists are missing.

## Turn (minimal)

```json
{
  "turn_index": 1,
  "speaker": "USER|COUNTERPARTY",
  "message_text": "string",
  "conversation": [{ "speaker": "USER", "text": "..." }],
  "outcome": "PASS|NEUTRAL|FAIL",
  "strategy_suggestions": [
    { "strategy_id": "STRAT_ID", "name": "Name", "summary": "..." }
  ],
  "used_strategies": ["STRAT_ID"]
}
```

## SimulationRun (minimal)

```json
{
  "run_id": "uuid",
  "case_id": "uuid",
  "seed": 123,
  "persona_id": "GENERIC",
  "turns": [ "... two turns ..." ],
  "outcome": "PASS|NEUTRAL|FAIL",
  "user_utility": 0.0,
  "summary": { "summary": "string", "key_points": ["string"] }
}
```
