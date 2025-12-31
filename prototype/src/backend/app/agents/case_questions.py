from __future__ import annotations

from typing import Dict

from app.agents.base import AgentBase
from app.agents.schemas import CaseQuestionsOutput


class CaseQuestionsAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="CaseQuestions", prompt_id="case_questions_v1", prompt_registry=prompt_registry, llm=llm)

    async def generate(self, topic: str, domain: str, channel: str) -> Dict[str, object]:
        variables = {
            "topic": topic,
            "domain": domain,
            "channel": channel,
        }
        fallback = {"questions": []}
        call, parsed_output = await self._build_call(
            variables,
            fallback,
            response_model=CaseQuestionsOutput,
        )
        if not isinstance(parsed_output, dict):
            parsed_output = fallback
        call.parsed_output = parsed_output
        return parsed_output
