# Agents

This document describes each backend agent, its responsibility, and the prompt it uses.
Prompt templates live in `prototype/data/prompts/` and are rendered via `PromptRegistry`.

## Roleplay Agents

### UserProxyAgent
- Purpose: Generates the USER-side message each turn (advocates for the user’s goals).
- Prompt: `userproxy_v1` (`prototype/data/prompts/userproxy_v1.md`)
- Output: `RoleplayOutput` (`message_text`, `action`, `used_strategies`)
- Used in: `SimulationEngine` user turns.

### CounterpartyAgent
- Purpose: Generates the COUNTERPARTY-side message each turn (responds with constraints).
- Prompt: `counterparty_v1` (`prototype/data/prompts/counterparty_v1.md`)
- Output: `RoleplayOutput` (`message_text`, `action`, `used_strategies`)
- Used in: `SimulationEngine` counterparty turns.

### WorldAgent
- Purpose: Evaluates outcomes, extracts structure, and summarizes/aggregates runs.
- Prompts:
  - Outcome evaluation: `world_v1` (`prototype/data/prompts/world_v1.md`)
  - Structured extraction: `world_extract_v1` (`prototype/data/prompts/world_extract_v1.md`)
  - Run summary: `world_summary_v1` (`prototype/data/prompts/world_summary_v1.md`)
  - Bucket insights: `world_bucket_insights_v1` (`prototype/data/prompts/world_bucket_insights_v1.md`)
- Output:
  - Outcome: `WorldOutcomeOutput`
  - Extraction: `WorldExtractOutput`
  - Summary: `WorldRunSummaryOutput`
  - Insights: `BucketInsightsOutput`
- Used in: `SimulationEngine` and insights pipeline.

## UI/Case Setup Helpers

### CaseQuestionsAgent
- Purpose: Generates ranked case snapshot questions from a user topic.
- Prompt: `case_questions_v1` (`prototype/data/prompts/case_questions_v1.md`)
- Output: `CaseQuestionsOutput`
- Used in: `POST /cases/snapshot/questions`

### CounterpartyHintsAgent
- Purpose: Generates case-specific examples for counterparty controls.
- Prompt: `counterparty_hints_v1` (`prototype/data/prompts/counterparty_hints_v1.md`)
- Output: `CounterpartyHintExamplesOutput`
- Used in: `GET /cases/{case_id}/counterparty/hints`

### UIConfigAgent
- Purpose: Generates UI control schema (labels, descriptions, examples).
- Prompt: `uiconfig_v1` (`prototype/data/prompts/uiconfig_v1.md`)
- Output: `UIConfigOutput`
- Used in: UI configuration generation (see `app/agents/uiconfig.py`).

### ExtractorAgent
- Purpose: Extracts persona signals from raw user text.
- Prompt: `extractor_v1` (`prototype/data/prompts/extractor_v1.md`)
- Output: `ExtractorOutput`
- Used in: persona signal extraction workflows.

## Shared Infrastructure

- `AgentBase` builds payloads and calls the LLM client.
- `LLMClient` sends OpenRouter requests with JSON schema validation.
- Prompt rendering and split behavior are defined in `PromptRegistry` and the `<<PROMPT_SPLIT>>` token.
