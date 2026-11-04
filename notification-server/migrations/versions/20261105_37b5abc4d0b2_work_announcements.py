"""work announcements

새 작품 알림을 팔로워에게 나눠 넣은 기록(#989). 작품 하나에 한 줄이고, 있으면 다시 나눠 넣지 않는다.

Revision ID: 37b5abc4d0b2
Revises: 7fe0cf7007c0
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '37b5abc4d0b2'
down_revision: str | Sequence[str] | None = '7fe0cf7007c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'work_announcements',
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_key', sa.String(length=128), nullable=False),
        sa.Column('creator_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('source', 'source_key', name=op.f('pk_work_announcements')),
    )
    op.create_index(op.f('ix_work_announcements_creator_id'), 'work_announcements', ['creator_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_work_announcements_creator_id'), table_name='work_announcements')
    op.drop_table('work_announcements')
