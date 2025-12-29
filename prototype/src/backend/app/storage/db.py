from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection with row access by name.

    The database file is created under the prototype directory if missing.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False allows FastAPI background threads to reuse the connection.
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize storage tables for cases, runs, and traces.

    Table schemas are intentionally simple; JSON payloads are stored as strings.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            revision INTEGER,
            created_at TEXT,
            status TEXT,
            data TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            case_id TEXT,
            persona_id TEXT,
            outcome TEXT,
            data TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            run_id TEXT PRIMARY KEY,
            run_trace TEXT,
            turn_traces TEXT,
            agent_call_traces TEXT
        )
        """
    )
    conn.commit()
    conn.close()
