from __future__ import annotations

import json
from typing import Any, Dict


def model_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert a Pydantic model or mapping into a JSON-serializable dict.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    if hasattr(obj, "dict"):
        return obj.dict(by_alias=True)
    if isinstance(obj, dict):
        return obj
    return json.loads(json.dumps(obj))


def deep_update(original: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge a nested update mapping into a base dictionary.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            original[key] = deep_update(original[key], value)
        else:
            original[key] = value
    return original


def safe_json_dumps(payload: Any) -> str:
    """Serialize a payload to JSON using ASCII-safe encoding.
    """
    return json.dumps(payload, ensure_ascii=True)


def safe_json_loads(payload: str) -> Any:
    """Parse a JSON string into a Python object.
    """
    return json.loads(payload)
