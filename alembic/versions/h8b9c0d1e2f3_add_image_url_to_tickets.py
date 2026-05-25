"""add image_url to tickets

Revision ID: h8b9c0d1e2f3
Revises: g7a8b9c0d1e2
Create Date: 2026-05-25 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'g7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add image_url column to tickets table."""
    op.add_column('tickets', sa.Column('image_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Drop image_url column from tickets table."""
    op.drop_column('tickets', 'image_url')
