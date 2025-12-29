from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional, Tuple, Type

import httpx
from pydantic import BaseModel

from app.core.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL


class LLMResponseError(RuntimeError):
    def __init__(self, message: str, raw_output: Optional[str] = None, response_json: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.response_json = response_json


class LLMClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60)
        self._endpoint = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"

    async def run(
        self,
        prompt_text: str,
        response_model: Optional[Type[BaseModel]] = None,
        messages: Optional[list[dict[str, str]]] = None,
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Execute a chat completion request against OpenRouter and return raw/parsed output plus metadata.
        """
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is required to run simulations.")

        resolved_messages = [{"role": "system", "content": prompt_text}]
        if messages:
            resolved_messages.extend(list(messages))

        if response_model is None:
            raise ValueError("response_model is required for LLMClient.run")
        schema = response_model.model_json_schema()
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": resolved_messages,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                },
            },
        }

        max_retries = 2
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            start_time = time.monotonic()
            try:
                response = await self._client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                latency_ms = (time.monotonic() - start_time) * 1000
                if response.status_code >= 400:
                    raise RuntimeError(f"OpenRouter error {response.status_code}: {response.text}")

                response_json = response.json()
                raw_output = json.dumps(response_json)
                if isinstance(response_json, dict) and response_json.get("error"):
                    error = response_json.get("error") or {}
                    message = error.get("message") or error.get("type") or str(error)
                    raise LLMResponseError(
                        f"OpenRouter error: {message}", raw_output=raw_output, response_json=response_json
                    )
                usage: Optional[Dict[str, Any]] = response_json.get("usage")
                content = self._extract_message_content(response_json)
                if not content:
                    raise LLMResponseError(
                        "OpenRouter response missing message content", raw_output=raw_output, response_json=response_json
                    )

                cleaned = self._strip_code_fence(content)
                try:
                    parsed_payload = json.loads(cleaned)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError(
                        f"OpenRouter response invalid JSON: {exc}", raw_output=raw_output, response_json=response_json
                    ) from exc
                validated = response_model.model_validate(parsed_payload)
                parsed_output = validated.model_dump()

                if usage is not None and hasattr(usage, "model_dump"):
                    usage = usage.model_dump()
                elif usage is not None and hasattr(usage, "dict"):
                    usage = usage.dict()

                meta = {
                    "model_params": {
                        "provider": "openrouter",
                        "model": OPENROUTER_MODEL,
                        "temperature": payload.get("temperature"),
                    },
                    "token_usage": usage,
                    "latency_ms": latency_ms,
                }
                return raw_output, parsed_output, meta
            except (LLMResponseError, ValueError) as exc:
                last_error = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise

        raise last_error or RuntimeError("LLM request failed after retries")

    @staticmethod
    def _extract_message_content(response_json: Dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        if not choices:
            return ""
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content") or part.get("value")
                    if isinstance(text, str):
                        parts.append(text)
            joined = "".join(parts)
            if joined.strip():
                return joined
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        reasoning_details = message.get("reasoning_details")
        if isinstance(reasoning_details, list) and reasoning_details:
            first = reasoning_details[0] or {}
            text = first.get("text") if isinstance(first, dict) else None
            if isinstance(text, str) and text.strip():
                return text
        legacy_text = choice.get("text")
        if isinstance(legacy_text, str):
            return legacy_text
        return ""

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return text
