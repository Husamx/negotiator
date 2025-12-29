from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel

from app.agents.llm import LLMClient, LLMResponseError
from app.agents.prompts import PromptRegistry


@dataclass
class AgentCallResult:
    prompt_id: str
    prompt_version: str
    prompt_text: str
    variables: Dict[str, Any]
    messages: Optional[list[dict[str, str]]]
    raw_output: str
    parsed_output: Dict[str, Any]
    model_params: Optional[Dict[str, Any]] = None
    validation_result: Dict[str, Any] = None
    token_usage: Optional[Dict[str, Any]] = None
    latency_ms: Optional[float] = None


def _coerce_dict(value: Any) -> Dict[str, Any]:
    """Best-effort coercion of an LLM output into a dict.
    """
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {"text": str(value)}


class AgentBase:
    PROMPT_SPLIT_TOKEN = "<<PROMPT_SPLIT>>"

    def __init__(self, agent_name: str, prompt_id: str, prompt_registry: PromptRegistry, llm: Optional[LLMClient] = None) -> None:
        self.agent_name = agent_name
        self.prompt_id = prompt_id
        self.prompt_registry = prompt_registry
        self.llm = llm or LLMClient()

    async def _build_call(
        self,
        variables: Dict[str, Any],
        fallback_parsed: Dict[str, Any],
        response_model: Optional[Type[BaseModel]] = None,
        messages: Optional[list[dict[str, str]]] = None,
        prompt_id_override: Optional[str] = None,
    ) -> Tuple[AgentCallResult, Dict[str, Any]]:
        """Render a prompt, optionally execute an LLM call, and return trace data.
        """
        prompt_id = prompt_id_override or self.prompt_id
        prompt = self.prompt_registry.render(prompt_id, variables)
        system_prompt, user_prompt = self._compose_payload(prompt.template, messages or [], self.agent_name)
        trace_messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        model_params = None
        token_usage = None
        latency_ms = None
        validation_result = {"status": "PASS"}
        try:
            raw_output, parsed_output, meta = await self.llm.run(
                system_prompt,
                response_model=response_model,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parsed_output = _coerce_dict(parsed_output)
            model_params = meta.get("model_params")
            token_usage = meta.get("token_usage")
            latency_ms = meta.get("latency_ms")
        except LLMResponseError as exc:
            raw_output = exc.raw_output or f"LLM_ERROR: {exc}"
            parsed_output = fallback_parsed
            validation_result = {"status": "FAIL", "reason": str(exc)}
        except Exception as exc:
            raw_output = f"LLM_ERROR: {exc}"
            parsed_output = fallback_parsed
            validation_result = {"status": "FAIL", "reason": "LLM error"}

        call = AgentCallResult(
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            prompt_text=system_prompt,
            variables=variables,
            messages=trace_messages,
            raw_output=raw_output,
            parsed_output=parsed_output,
            model_params=model_params,
            validation_result=validation_result,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )
        return call, parsed_output

    @staticmethod
    def _compose_payload(
        system_prompt: str,
        messages: list[dict[str, str]],
        agent_name: str,
    ) -> Tuple[str, str]:
        agent_label = {
            "UserProxy": "USER",
            "Counterparty": "COUNTERPARTY",
            "WorldAgent": "WORLDAGENT",
        }.get(agent_name, agent_name.upper())
        assistant_label = "USER" if agent_name == "UserProxy" else "COUNTERPARTY"
        user_label = "COUNTERPARTY" if agent_name == "UserProxy" else "USER"
        system_part, user_part = AgentBase._split_prompt(system_prompt)
        history_lines = ["CONVERSATION HISTORY (USER, COUNTERPARTY, WORLDAGENT):"]
        if not messages:
            history_lines.append("None")
        else:
            for msg in messages:
                role = msg.get("role") or "user"
                content = msg.get("content") or ""
                speaker = assistant_label if role == "assistant" else user_label
                history_lines.append(f"{speaker}: {content}")
        history_lines.append(f"You are {agent_label} for this call.")
        history_block = "\n".join(history_lines)
        user_sections = [section for section in [user_part.strip(), history_block.strip()] if section]
        user_payload = "\n\n".join(user_sections).strip()
        return system_part.strip(), user_payload

    @staticmethod
    def _split_prompt(rendered: str) -> Tuple[str, str]:
        token = AgentBase.PROMPT_SPLIT_TOKEN
        if token in rendered:
            system_part, user_part = rendered.split(token, 1)
            return system_part.rstrip(), user_part.lstrip()
        return rendered.strip(), ""
