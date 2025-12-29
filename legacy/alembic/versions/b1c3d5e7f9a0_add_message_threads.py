"""Add message threads and active thread tracking.

Revision ID: b1c3d5e7f9a0
Revises: e691a07c4161
Create Date: 2025-12-24
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c3d5e7f9a0"
down_revision = "e691a07c4161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "message_threads" not in tables:
        op.create_table(
            "message_threads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
            sa.Column("parent_thread_id", sa.Integer(), sa.ForeignKey("message_threads.id"), nullable=True),
            sa.Column("parent_message_id", sa.Integer(), nullable=True),
            sa.Column("variant", sa.String(length=10), nullable=True),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    message_cols = {col["name"] for col in inspector.get_columns("messages")}
    if "thread_id" not in message_cols:
        op.add_column("messages", sa.Column("thread_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(
                "fk_messages_thread_id",
                "messages",
                "message_threads",
                ["thread_id"],
                ["id"],
            )
        except Exception:
            pass

    session_cols = {col["name"] for col in inspector.get_columns("sessions")}
    if "active_thread_id" not in session_cols:
        op.add_column("sessions", sa.Column("active_thread_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(
                "fk_sessions_active_thread_id",
                "sessions",
                "message_threads",
                ["active_thread_id"],
                ["id"],
            )
        except Exception:
            pass

    inspector = sa.inspect(conn)
    message_cols = {col["name"] for col in inspector.get_columns("messages")}
    session_cols = {col["name"] for col in inspector.get_columns("sessions")}
    sessions = conn.execute(sa.text("SELECT id FROM sessions")).fetchall()
    for (session_id,) in sessions:
        root = conn.execute(
            sa.text(
                "SELECT id FROM message_threads WHERE session_id = :sid AND parent_thread_id IS NULL ORDER BY created_at LIMIT 1"
            ),
            {"sid": session_id},
        ).fetchone()
        if root is None:
            created_at = datetime.utcnow().isoformat(sep=" ")
            result = conn.execute(
                sa.text(
                    "INSERT INTO message_threads (session_id, created_at) VALUES (:sid, :created_at)"
                ),
                {"sid": session_id, "created_at": created_at},
            )
            thread_id = result.lastrowid
        else:
            thread_id = root[0]
        if "active_thread_id" in session_cols:
            conn.execute(
                sa.text("UPDATE sessions SET active_thread_id = :tid WHERE id = :sid"),
                {"tid": thread_id, "sid": session_id},
            )
        if "thread_id" in message_cols:
            conn.execute(
                sa.text("UPDATE messages SET thread_id = :tid WHERE session_id = :sid"),
                {"tid": thread_id, "sid": session_id},
            )


def downgrade() -> None:
    op.drop_constraint("fk_sessions_active_thread_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "active_thread_id")

    op.drop_constraint("fk_messages_thread_id", "messages", type_="foreignkey")
    op.drop_column("messages", "thread_id")

    op.drop_table("message_threads")
