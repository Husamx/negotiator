from __future__ import annotations

from typing import Any, Dict, Tuple

from app.agents.base import AgentBase, AgentCallResult
from app.agents.schemas import ExtractorOutput


class ExtractorAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="ExtractorAgent", prompt_id="extractor_v1", prompt_registry=prompt_registry, llm=llm)

    async def extract(self, text: str) -> Tuple[Dict[str, Any], AgentCallResult]:
        """Extract persona signals from user text via the extractor agent.
        """
        variables = {"text": text}
        call, parsed_output = await self._build_call(
            variables,
            {"signals": {}},
            response_model=ExtractorOutput,
        )
        return parsed_output, call
