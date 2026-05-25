"""Add slack_webhook_url column to org_configs.

Revision ID: i9c0d1e2f3g4
Revises: h8b9c0d1e2f3
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "i9c0d1e2f3g4"
down_revision = "h8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add slack_webhook_url to org_configs."""
    op.add_column("org_configs", sa.Column("slack_webhook_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove slack_webhook_url from org_configs."""
    op.drop_column("org_configs", "slack_webhook_url")
