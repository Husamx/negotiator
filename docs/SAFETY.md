# Safety & Guardrails (v0.1)

## 1. Standard vs Premium separation (core safety rule)
Standard must not produce:
- advice (“you should…”, “I recommend…”, “best move…”)
- critique/judgment (“you conceded too early…”)
- suggested replies for the user

Premium may produce advice, but must avoid:
- instructions for deception, coercion, or manipulation
- escalating harmful interpersonal dynamics

## 2. Roleplay prompt constraints (Standard)
Roleplay agent must:
- remain in character as the counterparty
- negotiate realistically
- ask clarifying questions when missing context
- NEVER tell the user what to do/say

## 3. “No-coaching” output filter (Standard)
Implement a post-generation check for banned patterns:
- “you should”
- “I recommend”
- “best approach”
- “try to”
- “your goal should be”
- “here’s what to say”
If detected:
- regenerate (preferred) or rewrite into in-character counterparty response

## 4. Sensitive situations
If user topic suggests:
- abuse/coercion
- stalking/harassment
- self-harm
- threats/violence

Then:
- roleplay must not help the user harm others
- keep responses de-escalatory
- present a gentle safety nudge where appropriate
- in Premium, coach must avoid manipulation tactics and may recommend seeking help/support

## 5. Privacy & memory trust
- Memory is user-controlled and review-gated.
- Do not store audio by default.
- Provide “Delete all memory” and honor it fully (including derived stores).
