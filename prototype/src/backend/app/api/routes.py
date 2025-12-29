from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.analytics.insights import compute_insights
from app.core.models import CalibrationRequest, CaseSnapshot, SimulationRequest
from app.core.utils import deep_update, model_to_dict
from app.services.strategy_registry import StrategyRegistry
from app.simulation.engine import SimulationEngine
from app.storage.repositories import CaseRepository, RunRepository, TraceRepository
from app.agents.prompts import PromptRegistry
from app.agents.world import WorldAgent
from app.agents.counterparty_hints import CounterpartyHintsAgent
from app.core.counterparty_controls import control_definitions_by_id

router = APIRouter()

case_repo = CaseRepository()
run_repo = RunRepository()
trace_repo = TraceRepository()
strategy_registry = StrategyRegistry()
prompt_registry = PromptRegistry()
engine = SimulationEngine(strategy_registry, prompt_registry)
counterparty_hints_agent = CounterpartyHintsAgent(prompt_registry)


class CaseUpdate(CaseSnapshot):
    pass


class CaseDeleteRequest(BaseModel):
    case_ids: List[str]


@router.get("/strategies")
def list_strategies():
    """Return strategy cards from the registry.

    The registry normalizes legacy strategy JSON into the v0.1 schema
    before returning the list.
    """
    return [model_to_dict(s) for s in strategy_registry.list()]


@router.post("/cases")
def create_case(case: CaseSnapshot):
    """Create and persist a CaseSnapshot.

    The request is validated by Pydantic; the stored payload is the
    normalized dict representation used by the simulator.
    """
    case_data = model_to_dict(case)
    case_repo.create(case_data)
    return case_data


@router.patch("/cases/{case_id}")
def update_case(case_id: str, payload: Dict[str, Any] = Body(...)):
    """Patch a case snapshot and bump revision/status.

    This performs a deep merge on known sections (issues/objectives/etc.)
    and marks the case READY if required fields are populated.
    """
    existing = case_repo.get(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Case not found")
    # Deep merge allows partial updates of nested objects like controls.
    updated = deep_update(existing, payload)
    updated["revision"] = existing.get("revision", 0) + 1
    updated["status"] = "READY" if _case_is_ready(updated) else existing.get("status", "DRAFT")
    case_repo.update(updated)
    return updated


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    """Fetch a case by id.

    Returns the full CaseSnapshot payload as stored.
    """
    existing = case_repo.get(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Case not found")
    return existing


@router.get("/cases")
def list_cases():
    """List all saved cases (full snapshots)."""
    return case_repo.list()


@router.post("/cases/delete")
def delete_cases(payload: CaseDeleteRequest):
    """Delete saved cases and associated runs/traces."""
    case_ids = payload.case_ids or []
    if not case_ids:
        return {"deleted_cases": 0, "deleted_runs": 0, "deleted_traces": 0}
    deleted_cases = case_repo.delete_many(case_ids)
    deleted_runs_total = 0
    deleted_traces_total = 0
    for case_id in case_ids:
        run_ids = run_repo.delete_for_case(case_id)
        deleted_runs_total += len(run_ids)
        deleted_traces_total += trace_repo.delete_for_runs(run_ids)
    return {
        "deleted_cases": deleted_cases,
        "deleted_runs": deleted_runs_total,
        "deleted_traces": deleted_traces_total,
    }


@router.post("/cases/{case_id}/persona/calibrate")
def calibrate_persona(case_id: str, calibration: CalibrationRequest):
    """Calibrate persona distribution and update the case snapshot.

    Uses the persona pack to map calibration answers into a weighted
    distribution and persists the result on the case.
    """
    case = case_repo.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    weights = case.get("counterparty_assumptions", {}).get("persona_distribution") or []
    if not weights:
        weights = [{"persona_id": "GENERIC", "weight": 1.0}]
    raw_answers = calibration.calibration.answers or {}
    answers = {key: value for key, value in raw_answers.items() if value and value != "unknown"}
    case["counterparty_assumptions"]["calibration"] = {"answers": answers}
    case["counterparty_assumptions"]["persona_distribution"] = [model_to_dict(w) for w in weights]
    case["revision"] = case.get("revision", 0) + 1
    case_repo.update(case)
    control_defs = control_definitions_by_id()
    control_lines = []
    for control_id, value in answers.items():
        definition = control_defs.get(control_id, {})
        label = definition.get("label", control_id)
        desc = definition.get("definition", "")
        if desc:
            control_lines.append(f"- {label}: {desc} Value: {value}")
        else:
            control_lines.append(f"- {label}: Value: {value}")
    controls_text = "None" if not control_lines else "\n".join(control_lines)
    return {
        "counterparty_controls_summary": f"counterparty_controls:\n{controls_text}",
    }


@router.get("/cases/{case_id}/counterparty/hints")
async def counterparty_hints(case_id: str):
    """Generate case-specific examples for counterparty controls."""
    case_data = case_repo.get(case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail="Case not found")
    case = CaseSnapshot(**case_data)
    hints_payload = await counterparty_hints_agent.generate(case)
    return hints_payload


@router.post("/cases/{case_id}/simulate")
async def simulate(case_id: str, request: SimulationRequest):
    """Run recorded simulations and persist runs and traces.

    Each run produces a SimulationRun plus a full trace bundle (run/turn/agent calls).
    """
    case_data = case_repo.get(case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail="Case not found")
    # Re-validate the stored case snapshot before simulation.
    case = CaseSnapshot(**case_data)
    runs_payload = []
    async for result in engine.run_stream(case, request.runs, request.max_turns, request.mode):
        run_data = model_to_dict(result.run)
        run_repo.add(run_data)
        trace_repo.add(run_data["run_id"], result.trace_bundle)
        runs_payload.append(run_data)
    # Mark case as simulated after all runs are persisted.
    case_data["status"] = "SIMULATED"
    case_repo.update(case_data)
    return runs_payload


@router.get("/cases/{case_id}/runs")
def list_runs(case_id: str):
    """List all runs for a given case.

    This is the lightweight list endpoint; use /runs/{id} for trace summary.
    """
    return run_repo.list_for_case(case_id)


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    """Return a run and its trace summary.

    The trace summary is the run_trace header, not the full trace bundle.
    """
    run = run_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    trace = trace_repo.get(run_id)
    trace_summary = trace["run_trace"] if trace else None
    return {"run": run, "trace_summary": trace_summary}


@router.get("/runs/{run_id}/trace")
def get_trace(run_id: str):
    """Return the full trace bundle for a run.

    Includes run_trace, turn_traces, and agent_call_traces.
    """
    trace = trace_repo.get(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/cases/{case_id}/insights")
async def get_insights(case_id: str):
    """Compute analytics and compromise levers for a case.

    Insights are computed from existing runs; what-if levers may trigger
    additional deterministic simulations.
    """
    case_data = case_repo.get(case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail="Case not found")
    case = CaseSnapshot(**case_data)
    runs = run_repo.list_for_case(case_id)
    insights = compute_insights(case, runs)
    insights["compromise_levers"] = _compute_compromise_levers(case, runs)
    insights["bucket_insights"] = await _compute_bucket_insights(case, runs)
    return insights


def _case_is_ready(case_data: Dict[str, Any]) -> bool:
    """Check required fields to determine READY status.

    This is a minimal completeness gate for UI flow, not a full schema validator.
    """
    required_fields = ["topic", "objectives", "parameters", "controls", "counterparty_assumptions"]
    for field in required_fields:
        value = case_data.get(field)
        if value in (None, "", [], {}):
            return False
    issues = case_data.get("issues")
    user_issues = case_data.get("user_issues")
    counterparty_issues = case_data.get("counterparty_issues")
    if issues in (None, "", [], {}):
        if user_issues in (None, "", [], {}) or counterparty_issues in (None, "", [], {}):
            return False
    return True


def _compute_compromise_levers(case: CaseSnapshot, runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compromise levers are not computed in minimal roleplay mode."""
    return []


async def _compute_bucket_insights(case: CaseSnapshot, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Use WorldAgent to derive insights for PASS/NEUTRAL/FAIL buckets."""
    if not runs:
        return {}
    world_agent = WorldAgent(prompt_registry)
    buckets: Dict[str, List[str]] = {"PASS": [], "NEUTRAL": [], "FAIL": []}
    for run in runs:
        outcome = str(run.get("outcome", "NEUTRAL"))
        summary = run.get("summary") or {}
        summary_text = summary.get("summary") or ""
        key_points = summary.get("key_points") or []
        if not summary_text and not key_points:
            continue
        run_id = run.get("run_id", "")
        key_points_text = "\n".join(f"- {item}" for item in key_points) if key_points else ""
        buckets.setdefault(outcome, []).append(
            "\n".join(
                [
                    f"run_id: {run_id}",
                    f"summary: {summary_text}",
                    f"key_points:\n{key_points_text}" if key_points_text else "key_points: None",
                ]
            ).strip()
        )

    results: Dict[str, Any] = {}
    for bucket, items in buckets.items():
        if not items:
            results[bucket] = {"bucket": bucket, "insights": []}
            continue
        variables = {
            "bucket": bucket,
            "summaries_text": "\n\n".join(items),
        }
        insight, _ = await world_agent.bucket_insights(variables)
        results[bucket] = insight
    return results
