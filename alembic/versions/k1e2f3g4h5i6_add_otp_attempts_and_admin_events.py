"""Add users.otp_attempts and the admin_events table.

otp_attempts enforces an OTP brute-force lockout; admin_events backs the
cross-worker admin SSE feed.

Revision ID: k1e2f3g4h5i6
Revises: j0d1e2f3g4h5
Create Date: 2026-11-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "k1e2f3g4h5i6"
down_revision = "j0d1e2f3g4h5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add otp_attempts column and admin_events table (idempotent).

    The app's startup ``Base.metadata.create_all`` can create admin_events before
    this migration runs, so each step checks the live schema first.
    """
    insp = sa.inspect(op.get_bind())
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "otp_attempts" not in user_cols:
        op.add_column(
            "users",
            sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
    if not insp.has_table("admin_events"):
        op.create_table(
            "admin_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("org_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        )


def downgrade() -> None:
    """Drop admin_events table and otp_attempts column."""
    op.drop_table("admin_events")
    op.drop_column("users", "otp_attempts")
