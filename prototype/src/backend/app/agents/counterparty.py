from __future__ import annotations

from typing import Any, Dict, Tuple

from app.core.models import ActionType
from app.agents.base import AgentBase, AgentCallResult
from app.agents.schemas import RoleplayOutput


class CounterpartyAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="Counterparty", prompt_id="counterparty_v1", prompt_registry=prompt_registry, llm=llm)

    async def roleplay(
        self,
        variables: Dict[str, Any],
        fallback_message: str,
        messages: list[dict[str, str]] | None = None,
    ) -> Tuple[str, AgentCallResult]:
        """Generate the counterparty roleplay message."""
        fallback_payload = {
            "action": {"type": ActionType.COUNTER_OFFER.value, "payload": {}},
            "message_text": fallback_message,
            "used_strategies": [],
        }
        call, parsed_output = await self._build_call(
            variables,
            fallback_payload,
            response_model=RoleplayOutput,
            messages=messages,
        )
        message_text = parsed_output.get("message_text") if isinstance(parsed_output, dict) else ""
        used_strategies = parsed_output.get("used_strategies") if isinstance(parsed_output, dict) else None
        action = parsed_output.get("action") if isinstance(parsed_output, dict) else None
        if not isinstance(message_text, str) or not message_text.strip():
            message_text = fallback_message
        if not isinstance(used_strategies, list):
            used_strategies = None
        else:
            used_strategies = [str(item) for item in used_strategies]
        if not isinstance(action, dict):
            action = fallback_payload.get("action")
        call.parsed_output = {"action": action, "message_text": message_text, "used_strategies": used_strategies}
        return message_text, call
