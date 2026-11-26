"""Add users.is_active (admins can deactivate departed employees).

Revision ID: m3g4h5i6j7k8
Revises: l2f3g4h5i6j7
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "m3g4h5i6j7k8"
down_revision = "l2f3g4h5i6j7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_active (idempotent — create_all may already have added it)."""
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "is_active" not in cols:
        op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    """Drop is_active."""
    op.drop_column("users", "is_active")
