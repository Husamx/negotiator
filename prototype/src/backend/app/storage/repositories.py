from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.utils import safe_json_dumps, safe_json_loads
from app.storage.db import get_connection


class CaseRepository:
    def create(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a new case snapshot record.
        """
        conn = get_connection()
        conn.execute(
            "INSERT INTO cases (case_id, revision, created_at, status, data) VALUES (?, ?, ?, ?, ?)",
            (
                case_data["case_id"],
                case_data["revision"],
                case_data["created_at"],
                case_data["status"],
                safe_json_dumps(case_data),
            ),
        )
        conn.commit()
        conn.close()
        return case_data

    def update(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing case snapshot record.
        """
        conn = get_connection()
        conn.execute(
            "UPDATE cases SET revision = ?, status = ?, data = ? WHERE case_id = ?",
            (
                case_data["revision"],
                case_data["status"],
                safe_json_dumps(case_data),
                case_data["case_id"],
            ),
        )
        conn.commit()
        conn.close()
        return case_data

    def get(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a case snapshot by case_id.
        """
        conn = get_connection()
        row = conn.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return safe_json_loads(row["data"])


class RunRepository:
    def add(self, run_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a run record.
        """
        conn = get_connection()
        conn.execute(
            "INSERT INTO runs (run_id, case_id, persona_id, outcome, data) VALUES (?, ?, ?, ?, ?)",
            (
                run_data["run_id"],
                run_data["case_id"],
                run_data["persona_id"],
                run_data["outcome"],
                safe_json_dumps(run_data),
            ),
        )
        conn.commit()
        conn.close()
        return run_data

    def list_for_case(self, case_id: str) -> List[Dict[str, Any]]:
        """List all runs associated with a case.
        """
        conn = get_connection()
        rows = conn.execute("SELECT data FROM runs WHERE case_id = ?", (case_id,)).fetchall()
        conn.close()
        return [safe_json_loads(row["data"]) for row in rows]

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a run record by run_id.
        """
        conn = get_connection()
        row = conn.execute("SELECT data FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return safe_json_loads(row["data"])


class TraceRepository:
    def add(self, run_id: str, trace_bundle: Dict[str, Any]) -> None:
        """Persist the trace bundle for a run.
        """
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO traces (run_id, run_trace, turn_traces, agent_call_traces) VALUES (?, ?, ?, ?)",
            (
                run_id,
                safe_json_dumps(trace_bundle["run_trace"]),
                safe_json_dumps(trace_bundle["turn_traces"]),
                safe_json_dumps(trace_bundle["agent_call_traces"]),
            ),
        )
        conn.commit()
        conn.close()

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the trace bundle for a run.
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT run_trace, turn_traces, agent_call_traces FROM traces WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "run_trace": safe_json_loads(row["run_trace"]),
            "turn_traces": safe_json_loads(row["turn_traces"]),
            "agent_call_traces": safe_json_loads(row["agent_call_traces"]),
        }
