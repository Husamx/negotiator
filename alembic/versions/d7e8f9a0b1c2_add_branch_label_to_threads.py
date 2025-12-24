"""Add branch_label to message threads.

Revision ID: d7e8f9a0b1c2
Revises: c4a1b2d3e4f5
Create Date: 2025-12-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7e8f9a0b1c2"
down_revision = "c4a1b2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("message_threads")}
    if "branch_label" not in columns:
        op.add_column("message_threads", sa.Column("branch_label", sa.String(length=120), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("message_threads")}
    if "branch_label" in columns:
        op.drop_column("message_threads", "branch_label")
