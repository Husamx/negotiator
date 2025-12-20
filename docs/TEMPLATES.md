# Templates (v0.1)

Templates define:
- which entities matter
- which information (slots) is needed
- what questions to ask (minimal)
- how roleplay should behave

## 1. Template JSON schema (conceptual)

Each template must define:

- `template_id` (string)
- `name` (string)
- `segment` = "20s"
- `entities`:
  - list of required roles (User, Counterparty)
  - optional roles (ThirdParty, SharedAsset, etc.)
- `slots`:
  - each slot: { key, label, required, priority, type, entity_role, skip_if }
- `question_policy`:
  - max_questions_typical (<=7)
  - ordering heuristic (importance/cost)
  - disambiguation_question (optional)
- `roleplay`:
  - default counterparty persona
  - typical objections
  - allowed tone styles
- `safety_notes`

## 2. Official template list (v0.1)

- roommate_conflict
- relationship_disagreement
- dating_expectations
- friendship_conflict
- money_with_friends
- family_parental_disagreement
- workplace_boundary
- salary_offer
- rent_renewal
- refund_complaint

## 3. “Other” generic template

### 3.1 Minimal slots
1) counterparty relationship + role
2) user goal
3) counterparty goal (as known)
4) user BATNA / fallback
5) constraints/boundaries

### 3.2 Question set
Ask up to 5 questions aligned to the above, then start roleplay.

## 4. Draft templates + proposal workflow (Template Agent)

### 4.1 TemplateDraft
- stored per user
- immediately usable for that user
- marked internally as `draft=true`

### 4.2 TemplateProposal
A proposal is either:
- new template (from Other)
- patch to an existing template (schema modification)

Proposal fields:
- `proposal_id`
- `based_on` = new_from_other | patch_existing
- `template_id_base` (if patch)
- `proposed_name`
- `entities`
- `slots`
- `question_policy`
- `roleplay` parameters
- `diff` (if patch)
- `evidence` (signals; no raw text required by default)
- timestamps

### 4.3 Trigger signals
- high `custom_slot_count`
- repeated missing slot clarifications
- high fact rejection/edit rate
- low “realism rating” (optional)
- router confidence low

See `docs/EVENTS.md` for how these are measured.
