"""Add action_label to message threads.

Revision ID: c4a1b2d3e4f5
Revises: b1c3d5e7f9a0
Create Date: 2025-12-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4a1b2d3e4f5"
down_revision = "b1c3d5e7f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("message_threads")}
    if "action_label" not in columns:
        op.add_column("message_threads", sa.Column("action_label", sa.String(length=80), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("message_threads")}
    if "action_label" in columns:
        op.drop_column("message_threads", "action_label")
