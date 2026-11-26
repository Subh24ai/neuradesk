"""Add user_sessions.user_agent and ip_address (device info for session list).

Revision ID: l2f3g4h5i6j7
Revises: k1e2f3g4h5i6
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "l2f3g4h5i6j7"
down_revision = "k1e2f3g4h5i6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add device columns (idempotent — create_all may already have added them)."""
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user_sessions")}
    if "user_agent" not in cols:
        op.add_column("user_sessions", sa.Column("user_agent", sa.String(length=300), nullable=True))
    if "ip_address" not in cols:
        op.add_column("user_sessions", sa.Column("ip_address", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop device columns."""
    op.drop_column("user_sessions", "ip_address")
    op.drop_column("user_sessions", "user_agent")
