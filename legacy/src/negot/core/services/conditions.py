"""
Evaluate boolean conditions used by strategy prerequisites and gates.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


def _get_path_value(data: Dict[str, Any], path: str) -> tuple[bool, Any]:
    if not path:
        return False, None
    if path.startswith("/"):
        path = path[1:]
    if not path:
        return True, data
    current: Any = data
    for raw_part in path.split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _check_min_confidence(value: Any, min_confidence: Optional[float]) -> bool:
    if min_confidence is None:
        return True
    if isinstance(value, dict) and "confidence" in value:
        try:
            return float(value["confidence"]) >= min_confidence
        except (TypeError, ValueError):
            return False
    return False


def _eval_predicate(predicate: Dict[str, Any], context: Dict[str, Any]) -> bool:
    op = predicate.get("op")
    path = predicate.get("path", "")
    exists, value = _get_path_value(context, path)
    if op == "EXISTS":
        return exists and value is not None
    if not exists:
        return False
    if not _check_min_confidence(value, predicate.get("min_confidence")):
        return False
    expected = predicate.get("value")
    values = predicate.get("values") or []
    if op == "EQ":
        return value == expected
    if op == "NEQ":
        return value != expected
    if op == "GT":
        return value > expected
    if op == "GTE":
        return value >= expected
    if op == "LT":
        return value < expected
    if op == "LTE":
        return value <= expected
    if op == "IN":
        return value in values
    if op == "CONTAINS":
        if isinstance(value, str) and isinstance(expected, str):
            return expected in value
        if isinstance(value, list):
            return expected in value
        return False
    if op == "MATCHES":
        regex = predicate.get("regex")
        if not regex:
            return False
        try:
            return re.search(regex, str(value)) is not None
        except re.error:
            return False
    return False


def evaluate_condition(condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
    condition_type = condition.get("type")
    if condition_type == "ALL":
        return all(evaluate_condition(item, context) for item in condition.get("all", []))
    if condition_type == "ANY":
        return any(evaluate_condition(item, context) for item in condition.get("any", []))
    if condition_type == "NOT":
        nested = condition.get("not")
        if not isinstance(nested, dict):
            return False
        return not evaluate_condition(nested, context)
    if condition_type == "PREDICATE":
        predicate = condition.get("predicate")
        if not isinstance(predicate, dict):
            return False
        return _eval_predicate(predicate, context)
    return False
