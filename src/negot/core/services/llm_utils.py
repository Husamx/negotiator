"""
Shared helpers for LiteLLM calls and response parsing.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from litellm import acompletion
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

LLM_RETRY_ATTEMPTS = 3


@retry(
    stop=stop_after_attempt(LLM_RETRY_ATTEMPTS),
    wait=wait_exponential(min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def acompletion_with_retry(**kwargs: Any) -> Any:
    return await acompletion(**kwargs)


def extract_completion_text(response: Any) -> Optional[str]:
    """Extract the text content from a LiteLLM completion response."""
    try:
        return response["choices"][0]["message"]["content"]
    except Exception:
        pass
    try:
        return response.choices[0].message.content
    except Exception:
        return None


def extract_json_object(content: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model output."""
    try:
        return json.loads(content)
    except Exception:
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = content[start : end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None
