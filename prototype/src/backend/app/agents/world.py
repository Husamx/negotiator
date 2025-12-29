from __future__ import annotations

from typing import Any, Dict, Tuple

from app.agents.base import AgentBase, AgentCallResult
from app.agents.schemas import (
    BucketInsightsOutput,
    WorldExtractOutput,
    WorldOutcomeOutput,
    WorldRunSummaryOutput,
    WorldValidationOutput,
)
from app.core.models import ActionTaken, CaseSnapshot, Outcome


class WorldAgent(AgentBase):
    def __init__(self, prompt_registry, llm=None) -> None:
        super().__init__(agent_name="WorldAgent", prompt_id="world_v1", prompt_registry=prompt_registry, llm=llm)

    async def validate(
        self,
        case: CaseSnapshot,
        action: ActionTaken,
        variables: Dict[str, Any],
    ) -> Tuple[bool, AgentCallResult]:
        """Validate feasibility of an action and return a trace record.
        """
        call, parsed_output = await self._build_call(
            variables,
            {"status": "PASS"},
            response_model=WorldValidationOutput,
        )
        status = parsed_output.get("status")
        call.validation_result = {"status": status or "PASS"}
        return status != "FAIL", call

    async def evaluate_outcome(
        self,
        variables: Dict[str, Any],
        messages: list[dict[str, str]] | None = None,
    ) -> Tuple[Outcome | None, AgentCallResult]:
        """Evaluate the negotiation outcome from conversation context."""
        call, parsed_output = await self._build_call(
            variables,
            {"outcome": Outcome.NEUTRAL.value},
            response_model=WorldOutcomeOutput,
            messages=messages,
        )
        if call.validation_result and call.validation_result.get("status") == "FAIL":
            return None, call
        outcome_raw = parsed_output.get("outcome") if isinstance(parsed_output, dict) else None
        outcome = None
        try:
            if isinstance(outcome_raw, str):
                outcome = Outcome(outcome_raw)
        except Exception:
            outcome = None
        call.parsed_output = {
            "outcome": outcome.value if outcome else Outcome.NEUTRAL.value,
            "reason": parsed_output.get("reason") if isinstance(parsed_output, dict) else None,
        }
        call.validation_result = {"status": "PASS"}
        return outcome, call

    async def extract_structure(
        self,
        variables: Dict[str, Any],
        messages: list[dict[str, str]] | None = None,
    ) -> Tuple[Dict[str, Any], AgentCallResult]:
        """Extract structured signals from the full conversation."""
        fallback = {
            "offers": [],
            "concessions": [],
            "packages": [],
            "asks": [],
            "objections": [],
            "arguments": [],
        }
        call, parsed_output = await self._build_call(
            variables,
            fallback,
            response_model=WorldExtractOutput,
            messages=messages,
            prompt_id_override="world_extract_v1",
        )
        if not isinstance(parsed_output, dict):
            parsed_output = fallback
        call.parsed_output = parsed_output
        return parsed_output, call

    async def summarize_run(
        self,
        variables: Dict[str, Any],
        messages: list[dict[str, str]] | None = None,
    ) -> Tuple[Dict[str, Any], AgentCallResult]:
        """Summarize a single run's conversation."""
        fallback = {"summary": "", "key_points": []}
        call, parsed_output = await self._build_call(
            variables,
            fallback,
            response_model=WorldRunSummaryOutput,
            messages=messages,
            prompt_id_override="world_summary_v1",
        )
        if not isinstance(parsed_output, dict):
            parsed_output = fallback
        call.parsed_output = parsed_output
        return parsed_output, call

    async def bucket_insights(
        self,
        variables: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], AgentCallResult]:
        """Generate insights for a single outcome bucket."""
        fallback = {"bucket": variables.get("bucket", ""), "insights": []}
        call, parsed_output = await self._build_call(
            variables,
            fallback,
            response_model=BucketInsightsOutput,
            messages=None,
            prompt_id_override="world_bucket_insights_v1",
        )
        if not isinstance(parsed_output, dict):
            parsed_output = fallback
        call.parsed_output = parsed_output
        return parsed_output, call
