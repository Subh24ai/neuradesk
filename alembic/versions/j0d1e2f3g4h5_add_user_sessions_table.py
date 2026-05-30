"""Add user_sessions table for session listing and remote revocation.

Revision ID: j0d1e2f3g4h5
Revises: i9c0d1e2f3g4
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "j0d1e2f3g4h5"
down_revision = "i9c0d1e2f3g4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_sessions table."""
    op.create_table(
        "user_sessions",
        sa.Column("jti", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop user_sessions table."""
    op.drop_table("user_sessions")
