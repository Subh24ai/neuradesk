"""add assignee_group and priority to tickets

Revision ID: e5f6a7b8c9d0
Revises: 847b88985b83
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: str | Sequence[str] | None = '847b88985b83'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tickets', sa.Column('assignee_group', sa.String(length=50), nullable=True))
    op.add_column('tickets', sa.Column('priority', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tickets', 'priority')
    op.drop_column('tickets', 'assignee_group')
