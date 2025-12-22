# Templates (v0.1)

Templates define:
- which entities matter
- which information (slots) is needed
- what questions to ask (minimal)
- how roleplay should behave
- when web grounding is typically useful (optional hint)

## 1. Template schema (conceptual)

Each template must define:
- template_id, name, segment
- entities (roles)
- slots (required/optional)
- question_policy (minimal, skip logic)
- roleplay params (persona, objections, tone)
- safety_notes
- optional: `web_grounding_hints` (e.g., culture/norms likely)

## 1.1 Unknown-aware template execution (required)
Templates must define required slots. Missing slots are UNKNOWN.
Question Planner outputs:
- unknown_required_slots[]
- questions[] (minimal to fill them)

Hard rule: agents must not invent values to satisfy readiness.

## 2. Official templates (v0.1)
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
Ask up to 5 questions then start roleplay. Do not infer counterparty goals if unknown.

## 4. Draft templates + proposal workflow
See `docs/ADMIN_REVIEW.md`.
