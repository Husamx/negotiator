# Safety & Guardrails (v0.1)

## 1. Standard vs Premium separation (core safety rule)
Standard must not produce:
- advice (“you should…”, “I recommend…”, “best move…”)
- critique/judgment (“you conceded too early…”)
- suggested replies for the user

Premium may produce advice, but must avoid:
- instructions for deception, coercion, or manipulation
- escalating harmful interpersonal dynamics

## 1.1 Unknown handling and grounding (applies to ALL agents)
**Unknown policy:** Any fact, attribute, relationship, or knowledge edge not explicitly present in the provided context is UNKNOWN.
Do not assume missing values, infer private details, or “fill in” plausible numbers.

**Grounding rule:** Any specific factual claim must be grounded in provided context or web sources.
If not grounded, ask a question or label it as an assumption/hypothesis.

### Implementation requirement: “no invented facts” validator
If generated output includes specific claims not present in:
- visible_facts (for roleplay)
- grounding_pack sources (for grounded statements)
then regenerate or rewrite to “unknown” / clarifying question.

## 2. Roleplay prompt constraints (Standard)
Roleplay agent must:
- remain in character as counterparty
- negotiate realistically
- ask clarifying questions when missing context
- NEVER tell the user what to do/say

## 3. “No-coaching” output filter (Standard)
Block banned coaching patterns:
- “you should”, “I recommend”, “best approach”, “try to”, “your goal should be”, “here’s what to say”

Also block “polite guessing” that invents missing values. If output uses terms like
“likely”, “probably”, “usually”, “most people”, etc. to imply a specific missing value
(e.g., guessing rent, salary, deadlines, intent), treat it as a violation and regenerate.
This does NOT apply to tone/behavior descriptions in character (“I’m usually busy”).

## 4. Sensitive situations
If topic suggests:
- abuse/coercion
- stalking/harassment
- self-harm
- threats/violence

Then:
- do not help harm others
- keep responses de-escalatory
- provide a gentle safety nudge where appropriate
- Premium coach avoids manipulation tactics and may recommend seeking support

## 5. Privacy & memory trust
- Memory is user-controlled and review-gated.
- Do not store raw web page content unless needed and with consent.
- Provide “Delete all memory” and honor it fully (including derived stores).
