# Negot Strategy System — Documentation (v1)

This folder contains a **complete strategy-template system** for negot plus a **CORE pack (30 strategies)**.

## Contents

- `schemas/` — JSON Schemas (Draft 2020-12) for:
  - Strategy packs and templates
  - Case snapshot (runtime input)
  - Strategy selection and execution I/O (agent contracts)
  - Artifacts, rubrics, and LLM-judge outputs
  - Conditions language for prerequisites/branching/gates
- `strategy_packs/core/` — CORE strategy pack:
  - `pack.json` (manifest)
  - `strategies/` (30 strategy templates)
  - `rubrics/` (message quality + safety rubrics)
  - `locales/en-GB.json` (minimal labels)

---

## 1) What “Strategy Templates” are

A strategy template is an executable playbook that:
- declares **when it applies** (domains/channels + prerequisites)
- defines **inputs** to collect (auto-bindable from case state)
- defines **steps** for an agent executor to run
- provides **scripts** (snippets/templates) that the drafting agent can reuse
- defines **branches** (“if they do X → recommend Y”)
- defines **evaluation** rules (rubrics + do-not-do + deterministic send-gates)

The result is **artifact-first negotiation**, not “just chat”.

---

## 2) Runtime state: CaseSnapshot

Strategies operate on a `CaseSnapshot`:
- parties (me/counterpart/stakeholders)
- issues (multi-issue support)
- objectives (target/acceptable/walk-away)
- constraints (policy/budget/deadlines)
- risk profile
- timeline events

This object is produced by intake/extraction agents elsewhere in negot.

---

## 3) Agent contracts (selection → execution → critique)

### 3.1 Selection
Input: `CaseSnapshot` + enabled strategies
Output: ranked strategies with rationale + failed prerequisites
Schema: `schemas/strategy_selection_io.schema.json`

### 3.2 Execution
Input: `CaseSnapshot` + a `StrategyTemplate` + inputs
Output:
- `artifacts[]` (message drafts, offer matrix, checklists, etc.)
- `case_patches[]` (JSON Patch RFC6902)
- `judge_outputs[]` (rubric-scored critique + flags)
Schema: `schemas/strategy_execution_io.schema.json`

---

## 4) Determinism vs “no heuristics”

Negot avoids brittle heuristics for extraction.  
However, **deterministic validation** is required and safe:
- schema validation
- prerequisite checks (conditions language)
- send-gates for obvious risk phrases (e.g., accidental bottom-line leaks)

Extraction remains agentic: the intake agent builds the `CaseSnapshot`.

---

## 5) CORE pack (30 strategies)

The CORE pack includes strategies across:
- Setup: process/timing leverage
- Information: interests/constraints/authority/criteria
- Value creation: MESOs, contingencies, unbundling, risk redesign
- Value claiming: anchors, bracketing, concessions, closing
- Communication: labeling/mirroring/summarizing/audits
- Deadlock: reframes, pauses, bridge-to-yes
- Multi-party: sequencing, coalitions, single-text
- Risk control: refusals, deferrals, professional walk-away

See: `strategy_packs/core/strategies/*.json`

---

## 6) How to load packs in the app

1) Load pack manifest:
- `strategy_packs/core/pack.json`
2) For each enabled strategy, load and validate against:
- `schemas/strategy_template.schema.json`
3) Load rubrics and locales similarly.
4) Expose strategies in UI:
- Library view (filter by category/tags)
- Case view: “Recommended strategies” + “Run strategy”

---

## 7) Minimum implementation checklist

- Schema validation on load + on all agent outputs
- Condition evaluator for prerequisites/branches/gates
- Artifact store + versioning
- Patch preview UI (diff) before applying JSON patches
- LLM judge runs on all outgoing drafts (quality + safety)

---

## 8) Notes on extensibility

- Add domain packs under `strategy_packs/domains/<domain>/...`
- Domain packs can override scripts, examples, and applicability defaults
- Keep `strategy_id` stable; bump `revision` for updates

