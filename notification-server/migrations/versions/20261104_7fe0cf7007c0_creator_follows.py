"""creator follows

제작자 팔로우(#989). 한 사람이 제작자 하나를 팔로우하면 한 줄이다. 자기 자신은 팔로우하지 않는다.

Revision ID: 7fe0cf7007c0
Revises: 7c2e4a9d1b6f
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7fe0cf7007c0'
down_revision: str | Sequence[str] | None = '7c2e4a9d1b6f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'creator_follows',
        sa.Column('follower_id', sa.Uuid(), nullable=False),
        sa.Column('creator_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('follower_id <> creator_id', name=op.f('ck_creator_follows_not_self')),
        sa.PrimaryKeyConstraint('follower_id', 'creator_id', name=op.f('pk_creator_follows')),
    )
    op.create_index(op.f('ix_creator_follows_creator_id'), 'creator_follows', ['creator_id'], unique=False)
    op.create_index(
        'ix_creator_follows_follower_created', 'creator_follows', ['follower_id', 'created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_creator_follows_follower_created', table_name='creator_follows')
    op.drop_index(op.f('ix_creator_follows_creator_id'), table_name='creator_follows')
    op.drop_table('creator_follows')
