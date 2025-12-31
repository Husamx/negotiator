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

    def list(self) -> List[Dict[str, Any]]:
        """List all case snapshots (newest first)."""
        conn = get_connection()
        rows = conn.execute("SELECT data FROM cases ORDER BY created_at DESC").fetchall()
        conn.close()
        return [safe_json_loads(row["data"]) for row in rows]

    def delete_many(self, case_ids: List[str]) -> int:
        """Delete cases by id. Returns the count removed."""
        if not case_ids:
            return 0
        placeholders = ",".join(["?"] * len(case_ids))
        conn = get_connection()
        cur = conn.execute(
            f"DELETE FROM cases WHERE case_id IN ({placeholders})",
            tuple(case_ids),
        )
        conn.commit()
        conn.close()
        return cur.rowcount or 0


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

    def update(self, run_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing run record."""
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET persona_id = ?, outcome = ?, data = ? WHERE run_id = ?",
            (
                run_data.get("persona_id"),
                run_data.get("outcome"),
                safe_json_dumps(run_data),
                run_data["run_id"],
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

    def delete_for_case(self, case_id: str) -> List[str]:
        """Delete runs for a case and return run_ids removed."""
        conn = get_connection()
        rows = conn.execute("SELECT run_id FROM runs WHERE case_id = ?", (case_id,)).fetchall()
        run_ids = [row["run_id"] for row in rows]
        conn.execute("DELETE FROM runs WHERE case_id = ?", (case_id,))
        conn.commit()
        conn.close()
        return run_ids


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

    def delete_for_runs(self, run_ids: List[str]) -> int:
        """Delete traces for a list of run_ids."""
        if not run_ids:
            return 0
        placeholders = ",".join(["?"] * len(run_ids))
        conn = get_connection()
        cur = conn.execute(
            f"DELETE FROM traces WHERE run_id IN ({placeholders})",
            tuple(run_ids),
        )
        conn.commit()
        conn.close()
        return cur.rowcount or 0


class PendingQuestionRepository:
    def add(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a pending question."""
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO pending_questions
            (question_id, case_id, run_id, session_id, status, asked_by, question, created_at, answer, answered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_data["question_id"],
                question_data["case_id"],
                question_data["run_id"],
                question_data["session_id"],
                question_data.get("status", "PENDING"),
                question_data.get("asked_by"),
                question_data.get("question"),
                question_data.get("created_at"),
                question_data.get("answer"),
                question_data.get("answered_at"),
            ),
        )
        conn.commit()
        conn.close()
        return question_data

    def list_for_case(self, case_id: str, session_id: Optional[str] = None, status: str = "PENDING") -> List[Dict[str, Any]]:
        """List pending questions for a case."""
        conn = get_connection()
        params: List[Any] = [case_id]
        query = "SELECT * FROM pending_questions WHERE case_id = ?"
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at ASC"
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def next_for_case(self, case_id: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the oldest pending question for a case/session."""
        conn = get_connection()
        params: List[Any] = [case_id, "PENDING"]
        query = "SELECT * FROM pending_questions WHERE case_id = ? AND status = ?"
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY created_at ASC LIMIT 1"
        row = conn.execute(query, tuple(params)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a question by id."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM pending_questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def mark_answered(self, question_id: str, answer: str, answered_at: str) -> Optional[Dict[str, Any]]:
        """Mark a pending question as answered."""
        conn = get_connection()
        conn.execute(
            """
            UPDATE pending_questions
            SET status = ?, answer = ?, answered_at = ?
            WHERE question_id = ?
            """,
            ("ANSWERED", answer, answered_at, question_id),
        )
        conn.commit()
        conn.close()
        return self.get(question_id)

    def count_for_session(self, session_id: str) -> int:
        """Count all asked questions for a session."""
        if not session_id:
            return 0
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as total FROM pending_questions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()
        return int(row["total"]) if row else 0

    def delete_for_case(self, case_id: str) -> int:
        """Delete questions for a case."""
        conn = get_connection()
        cur = conn.execute("DELETE FROM pending_questions WHERE case_id = ?", (case_id,))
        conn.commit()
        conn.close()
        return cur.rowcount or 0
