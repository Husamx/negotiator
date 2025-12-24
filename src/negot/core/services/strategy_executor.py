"""
Strategy execution using LLMs and deterministic gates.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text, extract_json_object
from .conditions import evaluate_condition

logger = logging.getLogger(__name__)

STRATEGY_EXECUTION_PROMPT = """You are the Strategy Execution agent.
Given the CaseSnapshot, StrategyTemplate, and inputs, produce execution outputs.
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


def _build_failure_response(
    *,
    strategy: dict,
    inputs: dict,
    case_id: str,
    reason: str,
    detail: str,
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

    payload = {
        "case_snapshot": case_snapshot,
        "strategy": strategy,
        "inputs": inputs,
        "rubrics": rubrics,
    }
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": STRATEGY_EXECUTION_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        "temperature": 0.3,
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
                )
    if execution is None:
        return _build_failure_response(
            strategy=strategy,
            inputs=inputs,
            case_id=case_id,
            reason="Strategy execution did not return a response.",
            detail="No response parsed from model output.",
        )
    if not isinstance(execution, StrategyExecutionIO):
        execution = StrategyExecutionIO.model_validate(execution)
    artifacts = _normalize_artifacts(execution.response.artifacts, strategy, inputs, case_id)
    judge_outputs = _apply_auto_gates(strategy, case_snapshot, artifacts, execution.response.judge_outputs)
    trace = execution.response.trace or {}
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
