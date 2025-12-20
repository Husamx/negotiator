# Admin Review Workflow (v0.1)

This describes the human-in-the-loop process for promoting draft templates to the official library.

## 1. Why review exists
- Draft templates are generated automatically and may be low quality or unsafe.
- Official templates must be consistent, minimal, and aligned to the app’s segment (20s).

## 2. Inputs
Template proposals are created by the Template Agent and stored as:
- `TemplateProposal` (see docs/TEMPLATES.md)

## 3. Internal tool requirements (minimal)
A simple internal UI (e.g., Streamlit) must allow an associate to:
- list proposals (sort by volume/impact)
- inspect proposal details + diff vs base template
- view evidence signals (coverage metrics, custom slot frequency, etc.)
- edit the proposed schema (slots, priorities, wording)
- approve / reject
- add notes (why rejected)

## 4. Outputs
- Approved proposal becomes an official template entry.
- Rejected proposals remain archived and are not surfaced to users.
- If edited then approved, store the edited version plus audit trail.

## 5. Audit
All admin actions must be logged:
- who approved/rejected
- when
- what changes were made
