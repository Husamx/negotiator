from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from app.core.models import CaseSnapshot


def _completed_runs(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [run for run in runs if run.get("status") != "PAUSED"]


def outcome_rates(runs: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute outcome rate distribution for a set of runs.
    """
    runs = _completed_runs(runs)
    total = max(len(runs), 1)
    counts = Counter(run["outcome"] for run in runs)
    return {
        "PASS": counts.get("PASS", 0) / total,
        "FAIL": counts.get("FAIL", 0) / total,
        "NEUTRAL": counts.get("NEUTRAL", 0) / total,
    }


def compute_outcome_rates(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute outcome rates overall and segmented by persona/strategy.
    """
    runs = _completed_runs(runs)
    by_persona: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        by_persona.setdefault(run.get("persona_id", "GENERIC"), []).append(run)
    return {
        "overall": outcome_rates(runs),
        "by_persona": [{"persona_id": pid, "rates": outcome_rates(items)} for pid, items in by_persona.items()],
    }


def compute_insights(case: CaseSnapshot, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assemble the full insights payload for a case.
    """
    runs = _completed_runs(runs)
    strategy_usage_summary = _compute_strategy_usage_summary(runs)
    return {
        "outcome_rates": compute_outcome_rates(runs),
        "utility_distribution": [run.get("user_utility", 0.0) for run in runs],
        "turns_to_termination": [len(run.get("turns", [])) for run in runs],
        "strategy_usage_summary": strategy_usage_summary,
    }


def _compute_strategy_usage_summary(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate per-strategy usage and outcome rates across runs."""
    strategy_stats: Dict[str, Dict[str, int]] = {}
    for run in runs:
        outcome = run.get("outcome", "NEUTRAL")
        turns = run.get("turns", []) or []
        used: set[str] = set()
        for turn in turns:
            for strat in turn.get("used_strategies") or []:
                used.add(str(strat))
        for strat in used:
            stats = strategy_stats.setdefault(strat, {"total": 0, "PASS": 0, "FAIL": 0, "NEUTRAL": 0})
            stats["total"] += 1
            if outcome in stats:
                stats[outcome] += 1
    summary: List[Dict[str, Any]] = []
    for strategy_id, stats in strategy_stats.items():
        total = max(stats["total"], 1)
        summary.append(
            {
                "strategy_id": strategy_id,
                "total_runs": stats["total"],
                "pass_rate": stats["PASS"] / total,
                "fail_rate": stats["FAIL"] / total,
                "neutral_rate": stats["NEUTRAL"] / total,
            }
        )
    summary.sort(key=lambda item: item.get("total_runs", 0), reverse=True)
    return summary
