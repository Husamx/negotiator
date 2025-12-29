from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from app.agents.counterparty import CounterpartyAgent
from app.agents.prompts import PromptRegistry
from app.agents.user_proxy import UserProxyAgent
from app.agents.world import WorldAgent
from app.core.config import MAX_PARALLEL_RUNS
from app.core.counterparty_controls import control_definitions_by_id
from app.core.models import CaseSnapshot, IssueDirection, Outcome, SimulationRun, Turn
from app.core.utils import model_to_dict
from app.services.strategy_registry import StrategyRegistry


@dataclass
class SimulationResult:
    run: SimulationRun
    trace_bundle: Dict[str, Any]


class SimulationEngine:
    """Minimal multi-round roleplay engine (single simulation)."""

    def __init__(self, strategy_registry: StrategyRegistry, prompt_registry: PromptRegistry, max_parallel: int | None = None) -> None:
        self.strategy_registry = strategy_registry
        self.prompt_registry = prompt_registry
        self.user_agent = UserProxyAgent(prompt_registry)
        self.counterparty_agent = CounterpartyAgent(prompt_registry)
        self.world_agent = WorldAgent(prompt_registry)
        self.max_parallel = max_parallel or MAX_PARALLEL_RUNS

    async def run(self, case: CaseSnapshot, runs: int, max_turns: int, mode: str) -> List[SimulationResult]:
        """Run multiple multi-round simulations for a case (async, parallelized)."""
        results: List[SimulationResult] = []
        async for result in self.run_stream(case, runs, max_turns, mode):
            results.append(result)
        return results

    async def run_stream(
        self, case: CaseSnapshot, runs: int, max_turns: int, mode: str
    ) -> AsyncIterator[SimulationResult]:
        """Yield simulation results as each run completes."""
        total_runs = max(1, int(runs))
        base_seed = self._base_seed(case.case_id)
        semaphore = asyncio.Semaphore(max(1, int(self.max_parallel)))

        async def _run_with_sem(seed: int) -> SimulationResult:
            async with semaphore:
                return await self._run_single(case, seed, max_turns)

        tasks = [asyncio.create_task(_run_with_sem(base_seed + offset)) for offset in range(total_runs)]
        try:
            for task in asyncio.as_completed(tasks):
                result = await task
                yield result
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

    async def _run_single(self, case: CaseSnapshot, seed: int, max_turns: int) -> SimulationResult:
        conversation: List[Dict[str, str]] = []
        turns: List[Turn] = []
        agent_call_traces: List[Dict[str, Any]] = []
        strategy_suggestions = self._strategy_suggestions(seed)
        clarifications_text = self._clarifications_text(case)
        latest_outcome = Outcome.NEUTRAL
        round_user_turn_index: Optional[int] = None

        max_turns = max(1, int(max_turns))
        for turn_index in range(1, max_turns + 1):
            is_user_turn = turn_index % 2 == 1
            if is_user_turn:
                user_variables = {
                    "topic": case.topic,
                    "domain": getattr(case.domain, "value", case.domain),
                    "channel": getattr(case.channel, "value", case.channel),
                    "issues_table": self._issues_table(self._issues_for_user(case)),
                    "parameters_table": self._parameters_table(case),
                    "target_summary": self._objective_summary(case, kind="target"),
                    "reservation_summary": self._objective_summary(case, kind="reservation"),
                    "clarifications": clarifications_text,
                    "strategy_suggestions": self._strategy_suggestions_text(strategy_suggestions),
                }
                user_fallback = self._user_fallback_message(case)
                user_messages = self._conversation_messages(conversation, assistant_speaker="USER")
                user_text, user_call = await self.user_agent.roleplay(
                    user_variables,
                    user_fallback,
                    messages=user_messages,
                )
                user_text = self._enforce_user_assertive(user_text, user_fallback)
                conversation.append({"speaker": "USER", "text": user_text})
                turns.append(
                    Turn(
                        turn_index=turn_index,
                        speaker="USER",
                        message_text=user_text,
                        conversation=list(conversation),
                        outcome=latest_outcome,
                        strategy_suggestions=strategy_suggestions,
                        used_strategies=self._extract_used_strategies(user_call),
                    )
                )
                agent_call_traces.append(self._trace_entry("UserProxy", user_call))
                round_user_turn_index = len(turns) - 1
            else:
                counter_variables = {
                    "topic": case.topic,
                    "domain": getattr(case.domain, "value", case.domain),
                    "channel": getattr(case.channel, "value", case.channel),
                    "issues_table": self._issues_table(self._issues_for_counterparty(case)),
                    "counterparty_assumptions_summary": self._counterparty_summary(case),
                    "clarifications": clarifications_text,
                    "strategy_suggestions": self._strategy_suggestions_text(strategy_suggestions),
                }
                counter_fallback = self._counterparty_fallback_message(case)
                counter_messages = self._conversation_messages(conversation, assistant_speaker="COUNTERPARTY")
                counter_text, counter_call = await self.counterparty_agent.roleplay(
                    counter_variables,
                    counter_fallback,
                    messages=counter_messages,
                )
                conversation.append({"speaker": "COUNTERPARTY", "text": counter_text})
                agent_call_traces.append(self._trace_entry("Counterparty", counter_call))

                world_variables = {
                    "topic": case.topic,
                    "domain": getattr(case.domain, "value", case.domain),
                    "channel": getattr(case.channel, "value", case.channel),
                    "issues_table": self._issues_table(self._issues_for_user(case)),
                    "target_summary": self._objective_summary(case, kind="target"),
                    "reservation_summary": self._objective_summary(case, kind="reservation"),
                    "primary_issue_id": self._primary_issue_id(case) or "",
                    "primary_issue_direction": self._primary_issue_direction(case),
                }
                world_messages = self._conversation_messages(conversation, assistant_speaker="COUNTERPARTY")
                world_outcome, world_call = await self.world_agent.evaluate_outcome(
                    world_variables,
                    messages=world_messages,
                )
                agent_call_traces.append(self._trace_entry("WorldAgent", world_call))
                latest_outcome = world_outcome or self._evaluate_outcome(case, conversation)

                if round_user_turn_index is not None:
                    turns[round_user_turn_index].outcome = latest_outcome
                    round_user_turn_index = None

                turns.append(
                    Turn(
                        turn_index=turn_index,
                        speaker="COUNTERPARTY",
                        message_text=counter_text,
                        conversation=list(conversation),
                        outcome=latest_outcome,
                        strategy_suggestions=strategy_suggestions,
                        used_strategies=self._extract_used_strategies(counter_call),
                    )
                )
                if latest_outcome in (Outcome.PASS, Outcome.FAIL):
                    break

        user_utility = self._utility_from_outcome(latest_outcome)
        extract_variables = {
            "topic": case.topic,
            "domain": getattr(case.domain, "value", case.domain),
            "channel": getattr(case.channel, "value", case.channel),
            "issues_table": self._issues_table(self._issues_for_user(case)),
        }
        extract_messages = self._conversation_messages(conversation, assistant_speaker="COUNTERPARTY")
        extraction, extract_call = await self.world_agent.extract_structure(
            extract_variables,
            messages=extract_messages,
        )
        agent_call_traces.append(self._trace_entry("WorldAgent", extract_call))
        summary, summary_call = await self.world_agent.summarize_run(
            extract_variables,
            messages=extract_messages,
        )
        agent_call_traces.append(self._trace_entry("WorldAgent", summary_call))
        run = SimulationRun(
            run_id=str(uuid.uuid4()),
            case_id=case.case_id,
            seed=seed,
            persona_id="GENERIC",
            turns=turns,
            outcome=latest_outcome,
            user_utility=user_utility,
            summary=summary,
        )
        trace_bundle = {
            "run_trace": {
                "seed": seed,
                "strategy_suggestions": strategy_suggestions,
                "extraction": extraction,
            },
            "turn_traces": [model_to_dict(t) for t in turns],
            "agent_call_traces": agent_call_traces,
        }
        return SimulationResult(run=run, trace_bundle=trace_bundle)

    def _trace_entry(self, agent_name: str, call) -> Dict[str, Any]:
        """Format a trace entry from an agent call result."""
        return {
            "agent_name": agent_name,
            "prompt_id": call.prompt_id,
            "prompt_version": call.prompt_version,
            "prompt_variables": call.variables,
            "prompt_text": call.prompt_text,
            "messages": call.messages,
            "raw_output": call.raw_output,
            "parsed_output": call.parsed_output,
            "model_params": getattr(call, "model_params", None),
            "validation_result": call.validation_result or {"status": "PASS"},
            "tool_calls": [],
            "token_usage": getattr(call, "token_usage", None),
            "latency_ms": getattr(call, "latency_ms", None),
        }

    def _base_seed(self, case_id: str) -> int:
        """Derive a deterministic seed from the case_id."""
        try:
            return int(uuid.UUID(case_id).int % 2**31)
        except Exception:
            digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
            return int(digest[:8], 16)

    def _strategy_suggestions(self, seed: int) -> List[Dict[str, Any]]:
        """Return a random sample of strategy summaries for prompt suggestions."""
        strategies = self.strategy_registry.list()
        if not strategies:
            return []
        rng = random.Random(seed)
        sample = rng.sample(strategies, k=min(4, len(strategies)))
        suggestions = []
        for item in sample:
            suggestions.append(
                {
                    "strategy_id": item.strategy_id,
                    "name": item.name,
                    "summary": item.summary,
                    "category": item.category,
                    "goal": item.goal,
                }
            )
        return suggestions

    def _strategy_suggestions_text(self, suggestions: List[Dict[str, Any]]) -> str:
        if not suggestions:
            return "None"
        lines = []
        for item in suggestions:
            strategy_id = item.get("strategy_id", "")
            name = item.get("name", "")
            summary = item.get("summary", "")
            category = item.get("category")
            goal = item.get("goal")
            line = f"- {strategy_id}: {name}. {summary}".strip()
            if category:
                line = f"{line} Category: {category}."
            if goal:
                line = f"{line} Goal: {goal}."
            lines.append(line.strip())
        return "\n".join(lines)

    def _conversation_messages(
        self,
        conversation: List[Dict[str, str]],
        assistant_speaker: str,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for msg in conversation:
            role = "assistant" if msg.get("speaker") == assistant_speaker else "user"
            messages.append({"role": role, "content": msg.get("text", "")})
        return messages

    def _issues_table(self, issues: List[Any]) -> str:
        if not issues:
            return "None"
        header = "issue_id | name | type | direction | unit | bounds"
        rows = [header]
        for issue in issues:
            issue_type = getattr(issue.type, "value", issue.type)
            direction = getattr(issue.direction, "value", issue.direction)
            unit = getattr(issue.unit, "value", issue.unit)
            bounds = ""
            if issue.bounds:
                bounds = f"{issue.bounds.min}..{issue.bounds.max}"
            rows.append(f"{issue.issue_id} | {issue.name} | {issue_type} | {direction} | {unit} | {bounds}")
        return "\n".join(rows)

    def _issues_for_user(self, case: CaseSnapshot) -> List[Any]:
        return list(case.user_issues or case.issues or [])

    def _issues_for_counterparty(self, case: CaseSnapshot) -> List[Any]:
        return list(case.counterparty_issues or case.issues or [])

    def _parameters_table(self, case: CaseSnapshot) -> str:
        if not case.parameters:
            return "None"
        header = "param_id | label | class | disclosure | value_type | value | scope | issue_id"
        rows = [header]
        for param in case.parameters:
            klass = getattr(param.class_, "value", param.class_)
            disclosure = getattr(param.disclosure, "value", param.disclosure)
            value_type = getattr(param.value_type, "value", param.value_type)
            scope = getattr(param.applies_to.scope, "value", param.applies_to.scope)
            issue_id = param.applies_to.issue_id or ""
            rows.append(
                f"{param.param_id} | {param.label} | {klass} | {disclosure} | {value_type} | {param.value} | {scope} | {issue_id}"
            )
        return "\n".join(rows)

    def _counterparty_summary(self, case: CaseSnapshot) -> str:
        calibration = case.counterparty_assumptions.calibration.answers or {}
        notes = case.counterparty_assumptions.notes or ""
        control_defs = control_definitions_by_id()
        control_lines = []
        for control_id, value in calibration.items():
            if value in (None, "", "unknown"):
                continue
            definition = control_defs.get(control_id, {})
            label = definition.get("label", control_id)
            desc = definition.get("definition", "")
            if desc:
                control_lines.append(f"- {label}: {desc} Value: {value}")
            else:
                control_lines.append(f"- {label}: Value: {value}")
        controls_text = "None" if not control_lines else "\n".join(control_lines)
        return "\n".join(
            [
                f"calibration_answers: {calibration}",
                "counterparty_controls:",
                controls_text,
                f"notes: {notes}",
            ]
        )

    def _clarifications_text(self, case: CaseSnapshot) -> str:
        clarifications = case.clarifications or []
        lines: List[str] = []
        for item in clarifications:
            question = getattr(item, "question", None) or ""
            answer = getattr(item, "answer", None)
            if not question or answer in (None, ""):
                continue
            answer_text = self._format_value(answer)
            lines.append(f"- Q: {question}\n  A: {answer_text}")
        return "\n".join(lines) if lines else "None"

    def _format_value(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    def _objective_summary(self, case: CaseSnapshot, kind: str) -> str:
        obj = case.objectives.reservation if kind == "reservation" else case.objectives.target
        obj_type = getattr(obj.type, "value", obj.type)
        if obj_type == "SINGLE_VALUE":
            return str(obj.value)
        if isinstance(obj.value, dict):
            return ", ".join(f"{key}={value}" for key, value in obj.value.items()) or "{}"
        return str(obj.value)

    def _user_fallback_message(self, case: CaseSnapshot) -> str:
        desired = self._objective_summary(case, kind="target")
        return f"I'm looking to reach {desired} on this offer and can explain why it makes sense."

    def _counterparty_fallback_message(self, case: CaseSnapshot) -> str:
        return "Thanks for outlining your goal. I need to balance this with internal constraints; here is a realistic counteroffer."

    def _enforce_user_assertive(self, message_text: str, fallback: str) -> str:
        if "?" in message_text:
            return fallback
        return message_text

    def _extract_used_strategies(self, call) -> Optional[List[str]]:
        parsed = getattr(call, "parsed_output", {}) or {}
        used = parsed.get("used_strategies")
        if isinstance(used, list):
            return [str(item) for item in used]
        return None

    def _evaluate_outcome(self, case: CaseSnapshot, conversation: List[Dict[str, str]]) -> Outcome:
        if not conversation:
            return Outcome.NEUTRAL
        latest_counter = next((msg["text"] for msg in reversed(conversation) if msg["speaker"] == "COUNTERPARTY"), "")
        target, reservation, direction = self._desired_values(case)
        offer_value = self._extract_offer_value(latest_counter, direction)
        if offer_value is None or target is None:
            return Outcome.NEUTRAL
        if direction == IssueDirection.MINIMIZE:
            if offer_value <= target:
                return Outcome.PASS
            if reservation is not None and offer_value <= reservation:
                return Outcome.NEUTRAL
            return Outcome.FAIL
        if offer_value >= target:
            return Outcome.PASS
        if reservation is not None and offer_value >= reservation:
            return Outcome.NEUTRAL
        return Outcome.FAIL

    def _desired_values(self, case: CaseSnapshot) -> Tuple[Optional[float], Optional[float], IssueDirection]:
        issues = self._issues_for_user(case)
        direction = issues[0].direction if issues else IssueDirection.MAXIMIZE
        target = None
        reservation = None
        target_type = getattr(case.objectives.target.type, "value", case.objectives.target.type)
        reservation_type = getattr(case.objectives.reservation.type, "value", case.objectives.reservation.type)
        if target_type == "SINGLE_VALUE":
            target = self._to_float(case.objectives.target.value)
        if reservation_type == "SINGLE_VALUE":
            reservation = self._to_float(case.objectives.reservation.value)
        if target_type == "OFFER_VECTOR" and isinstance(case.objectives.target.value, dict):
            issue_id = self._primary_issue_id(case)
            target = self._to_float(case.objectives.target.value.get(issue_id))
        if reservation_type == "OFFER_VECTOR" and isinstance(case.objectives.reservation.value, dict):
            issue_id = self._primary_issue_id(case)
            reservation = self._to_float(case.objectives.reservation.value.get(issue_id))
        return target, reservation, direction

    def _primary_issue_id(self, case: CaseSnapshot) -> Optional[str]:
        issues = self._issues_for_user(case)
        if not issues:
            return None
        weights = case.objectives.issue_weights or {}
        sorted_issues = sorted(issues, key=lambda issue: weights.get(issue.issue_id, 0.0), reverse=True)
        return sorted_issues[0].issue_id

    def _primary_issue_direction(self, case: CaseSnapshot) -> str:
        issues = self._issues_for_user(case)
        direction = issues[0].direction if issues else IssueDirection.MAXIMIZE
        return getattr(direction, "value", direction)

    def _extract_offer_value(self, text: str, direction: IssueDirection) -> Optional[float]:
        numbers = self._extract_numbers(text)
        if not numbers:
            return None
        return min(numbers) if direction == IssueDirection.MINIMIZE else max(numbers)

    def _extract_numbers(self, text: str) -> List[float]:
        tokens = []
        for raw in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", text or ""):
            value = self._to_float(raw)
            if value is not None:
                tokens.append(value)
        return tokens

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(str(value).replace(",", ""))
        except Exception:
            return None

    def _utility_from_outcome(self, outcome: Outcome) -> float:
        if outcome == Outcome.PASS:
            return 1.0
        if outcome == Outcome.FAIL:
            return 0.0
        return 0.5
