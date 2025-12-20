# Negotiator (working name)

Chat-based **role play** app for preparing for negotiations, debates, and arguments — tailored to people in their twenties.

- **Standard (default):** role play only (no coaching).
- **Premium:** role play + coaching (suggested replies, strategy, critique, scenario branches, after-action review).

This repository currently contains the **v0.1 product & technical requirements** (Markdown docs). Implementation will call an **external LLM provider** (no self-hosted model serving in v0.1).

## Repo contents

- `docs/REQUIREMENTS.md` — source-of-truth requirements (what to build)
- `docs/ARCHITECTURE.md` — proposed system architecture + orchestration
- `docs/DATA_MODEL.md` — KG + epistemic graph + event sourcing data model
- `docs/TEMPLATES.md` — template system, schemas, draft template workflow
- `docs/API.md` — API contract outline (HTTP + streaming)
- `docs/EVENTS.md` — telemetry & training signals (event taxonomy)
- `docs/SAFETY.md` — safety rules + Standard vs Premium guardrails
- `docs/ADMIN_REVIEW.md` — internal “template review” workflow (human-in-the-loop)

## Principles (non-negotiable)

1. **Chat-first UX**: every negotiation is a chat session.
2. **Memory is user-owned**: persistent Knowledge Graph (KG) with edit/delete; memory saving is review-gated.
3. **Realistic role play**: the counterparty only uses information they “know” (epistemic model).
4. **No coaching in Standard**: Standard must never output advice or critique.
5. **External LLM provider**: integrate via a provider-agnostic gateway interface.

## Status

**Brainstorm → spec drafting (v0.1).** Not yet implemented.

See `docs/REQUIREMENTS.md` for the full specification.
