from __future__ import annotations

import json
from typing import Dict, List

from app.agents.base import AgentBase
from app.agents.schemas import CounterpartyHint, CounterpartyHintExamplesOutput
from app.core.counterparty_controls import COUNTERPARTY_CONTROL_DEFINITIONS
from app.core.models import CaseSnapshot


CONTROL_DEFINITIONS: List[Dict[str, str]] = list(COUNTERPARTY_CONTROL_DEFINITIONS)


class CounterpartyHintsAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="CounterpartyHints", prompt_id="counterparty_hints_v1", prompt_registry=prompt_registry, llm=llm)

    async def generate(self, case: CaseSnapshot) -> Dict[str, object]:
        variables = {
            "topic": case.topic,
            "domain": getattr(case.domain, "value", case.domain),
            "channel": getattr(case.channel, "value", case.channel),
            "issues_table": self._issues_table(case),
            "parameters_table": self._parameters_table(case),
            "controls_reference": json.dumps(CONTROL_DEFINITIONS, ensure_ascii=True),
        }
        fallback_examples = {item["control_id"]: item["seed_example"] for item in CONTROL_DEFINITIONS}
        call, parsed_output = await self._build_call(
            variables,
            {"examples": fallback_examples},
            response_model=CounterpartyHintExamplesOutput,
        )
        examples = parsed_output.get("examples") or {}
        hints = []
        for item in CONTROL_DEFINITIONS:
            example = examples.get(item["control_id"]) or item["seed_example"]
            hints.append(
                CounterpartyHint(
                    control_id=item["control_id"],
                    label=item["label"],
                    definition=item["definition"],
                    example=example,
                ).model_dump()
            )
        return {"hints": hints}

    def _issues_table(self, case: CaseSnapshot) -> str:
        issues = list(case.user_issues or case.issues or [])
        if not issues:
            return "None"
        header = "issue_id | name | type | direction | unit | bounds"
        rows = [header]
        for issue in issues:
            issue_type = getattr(issue.type, "value", issue.type)
            direction = getattr(issue.direction, "value", issue.direction)
            unit = getattr(issue.unit, "value", issue.unit)
            bounds = ""
            if issue.bounds:
                bounds = f"{issue.bounds.min}..{issue.bounds.max}"
            rows.append(f"{issue.issue_id} | {issue.name} | {issue_type} | {direction} | {unit} | {bounds}")
        return "\n".join(rows)

    def _parameters_table(self, case: CaseSnapshot) -> str:
        if not case.parameters:
            return "None"
        header = "param_id | label | class | disclosure | value_type | value | scope | issue_id"
        rows = [header]
        for param in case.parameters:
            klass = getattr(param.class_, "value", param.class_)
            disclosure = getattr(param.disclosure, "value", param.disclosure)
            value_type = getattr(param.value_type, "value", param.value_type)
            scope = getattr(param.applies_to.scope, "value", param.applies_to.scope)
            issue_id = param.applies_to.issue_id or ""
            rows.append(
                f"{param.param_id} | {param.label} | {klass} | {disclosure} | {value_type} | {param.value} | {scope} | {issue_id}"
            )
        return "\n".join(rows)
