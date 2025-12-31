# API (Minimal Roleplay)

All endpoints use JSON.
Agent roles and prompts are listed in `docs/AGENTS.md`.

## POST /cases

Create a CaseSnapshot.

Minimal fields required:
- topic, domain, channel
- issues, objectives, parameters
- counterparty_assumptions, controls, mode

## PATCH /cases/{case_id}

Update parts of a case (issues/objectives/parameters/controls).

## POST /cases/{case_id}/simulate

Run a single simulation with multiple rounds (max turns set by user).

Request:
```json
{ "runs": 3, "max_turns": 2, "mode": "FAST" }
```

Response (per run):
```json
{
  "run_id": "uuid",
  "case_id": "uuid",
  "seed": 12345,
  "persona_id": "GENERIC",
  "turns": [
    {
      "turn_index": 1,
      "speaker": "USER",
      "message_text": "string",
      "conversation": [{ "speaker": "USER", "text": "..." }],
      "outcome": "PASS|NEUTRAL|FAIL"
    },
    {
      "turn_index": 2,
      "speaker": "COUNTERPARTY",
      "message_text": "string",
      "conversation": [
        { "speaker": "USER", "text": "..." },
        { "speaker": "COUNTERPARTY", "text": "..." }
      ],
      "outcome": "PASS|NEUTRAL|FAIL"
    }
  ],
  "outcome": "PASS|NEUTRAL|FAIL",
  "user_utility": 0.0
}
```

## GET /runs/{run_id}/trace

Returns full trace (prompt text + raw/parsed outputs).

## GET /strategies

Returns strategy cards from the registry.
