"""add token_blocklist table for JWT revocation

Revision ID: g7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-25 01:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'g7a8b9c0d1e2'
down_revision: str | Sequence[str] | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create token_blocklist table."""
    op.create_table(
        'token_blocklist',
        sa.Column('jti', sa.String(length=36), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('jti'),
    )


def downgrade() -> None:
    """Drop token_blocklist table."""
    op.drop_table('token_blocklist')
