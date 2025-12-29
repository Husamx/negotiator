from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from app.agents.base import AgentBase, AgentCallResult
from app.agents.schemas import UIConfigOutput


class UIConfigAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="UIConfigAgent", prompt_id="uiconfig_v1", prompt_registry=prompt_registry, llm=llm)

    async def configure(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentCallResult]:
        """Select relevant control sliders and defaults for the UI.
        """
        variables = dict(context or {})
        variables.setdefault("topic", "")
        variables.setdefault("domain", "")
        variables.setdefault("channel", "")
        variables.setdefault("issues_table", "")
        variables.setdefault("parameters_table", "")
        variables.setdefault("controls_summary", "")
        variables.setdefault("counterparty_assumptions_summary", "")
        variables.setdefault("context_json", json.dumps(context or {}, ensure_ascii=True))
        call, parsed_output = await self._build_call(
            variables,
            {"controls_ui": {}},
            response_model=UIConfigOutput,
        )
        return parsed_output, call
