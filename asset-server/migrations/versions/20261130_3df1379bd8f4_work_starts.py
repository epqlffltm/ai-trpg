"""work_starts

Revision ID: 3df1379bd8f4
Revises: b4d6f8a0c2e5
Create Date: 2026-11-30 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3df1379bd8f4'
down_revision: str | Sequence[str] | None = 'b4d6f8a0c2e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'work_starts',
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('work_id', sa.Uuid(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('recent', sa.Integer(), nullable=False),
        sa.Column('recent_days', sa.Integer(), nullable=False),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('character', 'world')", name=op.f('ck_work_starts_kind_allowed')),
        sa.CheckConstraint('total >= recent AND recent >= 0', name=op.f('ck_work_starts_counts_ordered')),
        sa.PrimaryKeyConstraint('kind', 'work_id', name=op.f('pk_work_starts')),
    )


def downgrade() -> None:
    op.drop_table('work_starts')
