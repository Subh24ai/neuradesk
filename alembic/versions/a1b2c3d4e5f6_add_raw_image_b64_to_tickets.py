"""add raw_image_b64 to tickets

Revision ID: a1b2c3d4e5f6
Revises: 98496fd33522
Create Date: 2026-05-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '98496fd33522'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add raw_image_b64 column to tickets table (nullable TEXT)."""
    op.add_column('tickets', sa.Column('raw_image_b64', sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop raw_image_b64 column from tickets table."""
    op.drop_column('tickets', 'raw_image_b64')
