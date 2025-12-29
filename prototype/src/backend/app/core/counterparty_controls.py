from __future__ import annotations

from typing import Dict, List

COUNTERPARTY_CONTROL_DEFINITIONS: List[Dict[str, str]] = [
    {
        "control_id": "policy_rigidity",
        "label": "Policy Rigidity",
        "definition": "How strictly the counterparty sticks to internal rules, bands, or approvals.",
        "seed_example": "Policy caps base salary at $130k, so we can adjust bonus but not base.",
    },
    {
        "control_id": "cooperativeness",
        "label": "Cooperativeness",
        "definition": "How collaborative vs guarded the counterparty's tone and posture are.",
        "seed_example": "We want to find a package that works for both sides and can trade across components.",
    },
    {
        "control_id": "time_pressure",
        "label": "Time Pressure",
        "definition": "How urgent the counterparty is to reach a decision and close.",
        "seed_example": "We need to finalize this offer by Friday to stay on our hiring timeline.",
    },
    {
        "control_id": "authority_clarity",
        "label": "Authority Clarity",
        "definition": "How clear the approval path is and whether the counterparty can commit.",
        "seed_example": "I can approve the base offer directly, but equity needs CFO sign-off.",
    },
]


def control_definitions_by_id() -> Dict[str, Dict[str, str]]:
    return {item["control_id"]: item for item in COUNTERPARTY_CONTROL_DEFINITIONS}
