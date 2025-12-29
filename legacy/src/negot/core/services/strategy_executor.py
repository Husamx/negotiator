"""
Strategy execution using LLMs and deterministic gates.
"""
from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object
from .conditions import evaluate_condition

logger = logging.getLogger(__name__)

STRATEGY_EXECUTION_PROMPT = """You are the Strategy Execution agent.
You receive a compacted CaseSnapshot, StrategyTemplate, and inputs (IDs removed, only salient fields included).
Produce execution outputs using this compact context.
Return JSON only matching this schema:
{"request":{"case_snapshot":{...},"strategy":{...},"inputs":{...}},
 "response":{"artifacts":[...],"case_patches":[...],"judge_outputs":[...],"trace":{...}}}

Rules:
- Use only provided evidence; do not invent facts.
- Generate artifacts required by the strategy steps (message drafts, checklists, etc).
- Provide rubric-based critique in judge_outputs.
- If prerequisites fail, return artifacts with remediation and empty case_patches.
"""


class StrategyExecutionRequest(BaseModel):
    case_snapshot: dict
    strategy: dict
    inputs: dict


class StrategyExecutionResponse(BaseModel):
    artifacts: List[dict] = Field(default_factory=list)
    case_patches: List[dict] = Field(default_factory=list)
    judge_outputs: List[dict] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)


class StrategyExecutionIO(BaseModel):
    request: StrategyExecutionRequest
    response: StrategyExecutionResponse


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _truncate_text(value: object, max_len: int = 500) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _compact_event(event: dict) -> dict:
    if not isinstance(event, dict):
        return {"summary": _truncate_text(event)}
    event_type = event.get("type")
    raw_text = event.get("raw_text") or event.get("summary") or ""
    speaker = "unknown"
    if event_type == "MESSAGE_IN":
        speaker = "counterparty"
    elif event_type == "MESSAGE_OUT":
        speaker = "user"
    return {
        "type": event_type,
        "speaker": speaker,
        "summary": _truncate_text(event.get("summary") or raw_text, 240),
        "raw_text": _truncate_text(raw_text, 480),
        "ts": event.get("ts"),
    }


def _compact_case_snapshot(case_snapshot: dict, max_events: int = 6) -> dict:
    objectives = case_snapshot.get("objectives") or {}
    issues = case_snapshot.get("issues") or []
    constraints = case_snapshot.get("constraints") or []
    timeline = case_snapshot.get("timeline") or {}
    events = timeline.get("recent_events") or []
    compact_events = [_compact_event(event) for event in events[-max_events:]]
    constraint_list = []
    for constraint in constraints:
        if isinstance(constraint, dict):
            desc = constraint.get("description") or ""
            if desc:
                constraint_list.append(_truncate_text(desc, 240))
        elif constraint:
            constraint_list.append(_truncate_text(constraint, 240))
    compact_issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            compact_issues.append({"name": _truncate_text(issue, 200)})
            continue
        compact_issues.append(
            {
                "name": _truncate_text(issue.get("name"), 200),
                "type": issue.get("type"),
                "my_position": _truncate_text(issue.get("my_position"), 280),
                "their_position": _truncate_text(issue.get("their_position"), 280),
                "my_interest": _truncate_text(issue.get("my_interest"), 240),
                "their_interest": _truncate_text(issue.get("their_interest"), 240),
            }
        )
    parties = case_snapshot.get("parties") or {}
    counterpart = parties.get("counterpart") or {}
    return {
        "domain": case_snapshot.get("domain"),
        "channel": case_snapshot.get("channel"),
        "stage": case_snapshot.get("stage"),
        "objectives": {
            "target": objectives.get("target"),
            "acceptable": objectives.get("acceptable"),
            "walk_away": objectives.get("walk_away"),
            "notes": _truncate_text(objectives.get("notes"), 240),
        },
        "issues": compact_issues,
        "constraints": constraint_list,
        "risk_profile": case_snapshot.get("risk_profile"),
        "counterparty": {
            "role": counterpart.get("role"),
            "stance": counterpart.get("stance"),
            "constraints": counterpart.get("constraints"),
        },
        "timeline": {"recent_events": compact_events},
    }


def _compact_strategy(strategy: dict, inputs: dict) -> dict:
    inputs_brief = []
    for item in strategy.get("inputs", []):
        key = item.get("key")
        if not key:
            continue
        value = inputs.get(key)
        if isinstance(value, list):
            value = ", ".join([_truncate_text(v, 120) for v in value])
        inputs_brief.append(
            {
                "label": item.get("label") or key,
                "required": item.get("required", False),
                "value": _truncate_text(value, 320),
                "help": _truncate_text(item.get("help"), 200),
            }
        )
    steps = []
    for step in strategy.get("steps", []):
        tools = [action.get("tool") for action in step.get("agent_actions", []) if action.get("tool")]
        steps.append(
            {
                "title": step.get("title"),
                "instruction": _truncate_text(step.get("instruction"), 360),
                "tools": tools,
            }
        )
    branches = []
    for branch in strategy.get("branches", []):
        recommended = branch.get("recommended_move") or {}
        branches.append(
            {
                "label": branch.get("label"),
                "recommended_move": recommended.get("instruction") or recommended.get("move_type"),
                "risk_notes": _truncate_text(branch.get("risk_notes"), 200),
            }
        )
    evaluation = strategy.get("evaluation") or {}
    auto_gates = []
    for gate in evaluation.get("auto_gates") or []:
        auto_gates.append(
            {
                "gate_id": gate.get("gate_id"),
                "description": gate.get("description"),
                "severity": gate.get("severity"),
            }
        )
    return {
        "strategy_id": strategy.get("strategy_id"),
        "name": strategy.get("name"),
        "summary": _truncate_text(strategy.get("summary"), 260),
        "goal": _truncate_text(strategy.get("goal"), 220),
        "inputs": inputs_brief,
        "steps": steps,
        "branches": branches,
        "evaluation": {
            "success_criteria": evaluation.get("success_criteria") or [],
            "failure_modes": evaluation.get("failure_modes") or [],
            "do_not_do": evaluation.get("do_not_do") or [],
            "auto_gates": auto_gates,
        },
    }


def _compact_rubrics(rubrics: List[dict]) -> List[dict]:
    compact = []
    for rubric in rubrics:
        compact.append(
            {
                "rubric_id": rubric.get("rubric_id"),
                "name": rubric.get("name"),
                "dimensions": [
                    {
                        "label": dim.get("label"),
                        "description": _truncate_text(dim.get("description"), 200),
                    }
                    for dim in rubric.get("dimensions", [])
                ],
            }
        )
    return compact


def _build_failure_response(
    *,
    strategy: dict,
    inputs: dict,
    case_id: str,
    reason: str,
    detail: str,
    model_request: dict | None = None,
    model_output_raw: str | None = None,
) -> StrategyExecutionResponse:
    artifact = {
        "artifact_id": f"ARTIFACT_{strategy['strategy_id']}_ERROR",
        "type": "CHECKLIST",
        "title": "Execution failed",
        "created_at": _now_iso(),
        "content": {
            "items": [
                {
                    "id": "EXECUTION_PARSE_ERROR",
                    "description": reason,
                    "remediation": "Check model configuration or retry the run.",
                    "severity": "BLOCKER",
                    "detail": detail[:500],
                }
            ]
        },
        "metadata": {
            "case_id": case_id,
            "strategy_id": strategy["strategy_id"],
            "strategy_revision": strategy.get("revision", 1),
            "inputs_used": inputs,
        },
    }
    return StrategyExecutionResponse(
        artifacts=[artifact],
        case_patches=[],
        judge_outputs=[
            {
                "rubric_id": "EXECUTION_ERROR",
                "overall_score": 0,
                "dimension_scores": [],
                "flags": [
                    {
                        "flag_id": "EXECUTION_PARSE_ERROR",
                        "severity": "BLOCK_SEND",
                        "message": reason,
                        "span_hint": "draft_text",
                    }
                ],
                "suggestions": [],
            }
        ],
        trace={
            "strategy_id": strategy["strategy_id"],
            "strategy_revision": strategy.get("revision", 1),
            "inputs_used": inputs,
            "generated_at": _now_iso(),
            "blocked": True,
            "error": reason,
            "error_detail": detail[:500],
            "model_request": model_request,
            "model_output_raw": model_output_raw[:800] if model_output_raw else None,
        },
    )


def _coerce_execution_payload(
    extracted: dict, case_snapshot: dict, strategy: dict, inputs: dict
) -> dict:
    if "request" in extracted and "response" in extracted:
        return extracted
    if "response" in extracted:
        return {
            "request": {"case_snapshot": case_snapshot, "strategy": strategy, "inputs": inputs},
            "response": extracted.get("response") or {},
        }
    if any(key in extracted for key in ("artifacts", "case_patches", "judge_outputs", "trace")):
        return {
            "request": {"case_snapshot": case_snapshot, "strategy": strategy, "inputs": inputs},
            "response": extracted,
        }
    return extracted


def _failed_prereqs(strategy: dict, case_snapshot: dict) -> List[dict]:
    failed = []
    for prereq in strategy.get("applicability", {}).get("prerequisites", []):
        condition = prereq.get("condition") or {}
        if not evaluate_condition(condition, case_snapshot):
            failed.append(prereq)
    return failed


def _normalize_artifacts(
    artifacts: List[dict], strategy: dict, inputs: dict, case_id: str
) -> List[dict]:
    normalized = []
    for idx, artifact in enumerate(artifacts, start=1):
        artifact_id = artifact.get("artifact_id") or f"ARTIFACT_{strategy['strategy_id']}_{idx}"
        created_at = artifact.get("created_at") or _now_iso()
        metadata = artifact.get("metadata") or {}
        metadata.setdefault("case_id", case_id)
        metadata.setdefault("strategy_id", strategy["strategy_id"])
        metadata.setdefault("strategy_revision", strategy.get("revision", 1))
        metadata.setdefault("inputs_used", inputs)
        artifact["artifact_id"] = artifact_id
        artifact["created_at"] = created_at
        artifact["metadata"] = metadata
        normalized.append(artifact)
    return normalized


def _apply_auto_gates(
    strategy: dict,
    case_snapshot: dict,
    artifacts: List[dict],
    judge_outputs: List[dict],
) -> List[dict]:
    auto_gates = strategy.get("evaluation", {}).get("auto_gates") or []
    if not auto_gates or not artifacts:
        return judge_outputs
    flags = []
    for artifact in artifacts:
        if artifact.get("type") != "MESSAGE_DRAFT":
            continue
        draft_text = ""
        content = artifact.get("content") or {}
        if isinstance(content, dict):
            draft_text = content.get("text") or ""
        context = dict(case_snapshot)
        context["execution_context"] = {"draft_text": draft_text}
        for gate in auto_gates:
            condition = gate.get("condition") or {}
            if evaluate_condition(condition, context):
                flags.append(
                    {
                        "flag_id": gate.get("gate_id", "AUTO_GATE"),
                        "severity": gate.get("severity", "WARN"),
                        "message": gate.get("description", "Auto gate triggered."),
                        "span_hint": "draft_text",
                    }
                )
    if not flags:
        return judge_outputs
    if not judge_outputs:
        judge_outputs.append(
            {
                "rubric_id": "AUTO_GATES",
                "overall_score": 0,
                "dimension_scores": [],
                "flags": flags,
                "suggestions": [],
            }
        )
        return judge_outputs
    for output in judge_outputs:
        output.setdefault("flags", []).extend(flags)
    return judge_outputs


async def execute_strategy(
    *,
    case_snapshot: dict,
    strategy: dict,
    inputs: dict,
    rubrics: List[dict],
) -> StrategyExecutionResponse:
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot execute strategy.")

    case_id = case_snapshot.get("case_id", "CASE_UNKNOWN")
    failed_prereqs = _failed_prereqs(strategy, case_snapshot)
    if failed_prereqs:
        remediation = [
            {
                "id": prereq.get("id"),
                "description": prereq.get("description"),
                "remediation": prereq.get("remediation"),
                "severity": prereq.get("severity"),
            }
            for prereq in failed_prereqs
        ]
        artifacts = [
            {
                "artifact_id": f"ARTIFACT_{strategy['strategy_id']}_BLOCKED",
                "type": "CHECKLIST",
                "title": "Prerequisites required before execution",
                "created_at": _now_iso(),
                "content": {"items": remediation},
                "metadata": {
                    "case_id": case_id,
                    "strategy_id": strategy["strategy_id"],
                    "strategy_revision": strategy.get("revision", 1),
                    "inputs_used": inputs,
                },
            }
        ]
        return StrategyExecutionResponse(
            artifacts=artifacts,
            case_patches=[],
            judge_outputs=[],
            trace={
                "strategy_id": strategy["strategy_id"],
                "strategy_revision": strategy.get("revision", 1),
                "inputs_used": inputs,
                "generated_at": _now_iso(),
                "blocked": True,
            },
        )

    full_input_payload = {
        "case_snapshot": case_snapshot,
        "strategy": strategy,
        "inputs": inputs,
        "rubrics": rubrics,
    }
    compact_payload = {
        "case_snapshot": _compact_case_snapshot(case_snapshot),
        "strategy": _compact_strategy(strategy, inputs),
        "rubrics": _compact_rubrics(rubrics),
    }
    compact_payload_text = json.dumps(compact_payload, default=str)
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": STRATEGY_EXECUTION_PROMPT},
            {"role": "user", "content": compact_payload_text},
        ],
        "temperature": 0.3,
    }
    model_request_payload = {
        "model": completion_kwargs.get("model"),
        "temperature": completion_kwargs.get("temperature"),
        "messages": completion_kwargs.get("messages", []),
        "input_payload": compact_payload,
        "full_input_hash": _hash_payload(full_input_payload),
        "compact_chars": len(compact_payload_text),
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    execution = None
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        execution = await client(response_model=StrategyExecutionIO, **completion_kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Instructor parsing failed for strategy execution: %s", exc)
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty strategy execution output.")
        try:
            execution = StrategyExecutionIO.model_validate_json(content)
        except Exception as parse_exc:  # noqa: BLE001
            logger.warning("Failed to parse strategy execution output. Error: %s", parse_exc)
            extracted = extract_json_object(content)
            if extracted is None:
                return _build_failure_response(
                    strategy=strategy,
                    inputs=inputs,
                    case_id=case_id,
                    reason="Strategy execution output was not valid JSON.",
                    detail=f"{parse_exc}. raw_output_preview={content[:400]}",
                    model_request=model_request_payload,
                    model_output_raw=content,
                )
            payload = _coerce_execution_payload(extracted, case_snapshot, strategy, inputs)
            try:
                execution = StrategyExecutionIO.model_validate(payload)
            except Exception as inner_exc:  # noqa: BLE001
                return _build_failure_response(
                    strategy=strategy,
                    inputs=inputs,
                    case_id=case_id,
                    reason="Strategy execution output did not match the expected schema.",
                    detail=str(inner_exc),
                    model_request=model_request_payload,
                    model_output_raw=content,
                )
    if execution is None:
        return _build_failure_response(
            strategy=strategy,
            inputs=inputs,
            case_id=case_id,
            reason="Strategy execution did not return a response.",
            detail="No response parsed from model output.",
            model_request=model_request_payload,
        )
    if not isinstance(execution, StrategyExecutionIO):
        execution = StrategyExecutionIO.model_validate(execution)
    artifacts = _normalize_artifacts(execution.response.artifacts, strategy, inputs, case_id)
    judge_outputs = _apply_auto_gates(strategy, case_snapshot, artifacts, execution.response.judge_outputs)
    trace = execution.response.trace or {}
    trace.setdefault("model_request", model_request_payload)
    trace.setdefault("full_input_hash", model_request_payload.get("full_input_hash"))
    trace.setdefault("compact_chars", model_request_payload.get("compact_chars"))
    if "model_response" not in trace:
        trace["model_response"] = execution.response.model_dump(exclude={"trace"})
    trace.setdefault("strategy_id", strategy["strategy_id"])
    trace.setdefault("strategy_revision", strategy.get("revision", 1))
    trace.setdefault("inputs_used", inputs)
    trace.setdefault("generated_at", _now_iso())
    return StrategyExecutionResponse(
        artifacts=artifacts,
        case_patches=execution.response.case_patches,
        judge_outputs=judge_outputs,
        trace=trace,
    )
