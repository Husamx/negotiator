# Admin Review Workflow (v0.1)

Human-in-the-loop process for promoting draft templates to the official library.

## 1. Inputs
Template proposals (`TemplateProposal`) created by Template Agent.

## 2. Internal tool (minimal)
A simple internal UI (e.g., Streamlit) must allow:
- list proposals
- inspect proposal details + diff vs base template
- view evidence signals (custom slot frequency, low confidence routing)
- edit schema (slots, priorities, wording)
- approve / reject
- add notes

## 3. Outputs
- Approved → becomes official template
- Rejected → archived
- Edited+approved → store edited version + audit trail

## 4. Audit
Log admin actions: who/when/what changes.
