"""portraits

제작자가 올린 캐릭터 그림의 기록(#983). 그림은 asset 서버에 있고 id 가 같다.

Revision ID: 7c3e9a1f5b20
Revises: d1e6b97b1ed6
Create Date: 2026-12-05 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7c3e9a1f5b20'
down_revision: str | Sequence[str] | None = 'd1e6b97b1ed6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'portraits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_portraits')),
    )
    op.create_index('ix_portraits_owner_created', 'portraits', ['owner_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_portraits_owner_created', table_name='portraits')
    op.drop_table('portraits')
