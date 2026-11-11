"""table quests

Revision ID: 4023c8b48079
Revises: cd307cbf3323
Create Date: 2026-10-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4023c8b48079'
down_revision: str | Sequence[str] | None = 'cd307cbf3323'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 진행 중인 테이블에는 퀘스트를 만들지 않는다. 퀘스트는 시작할 때 판의 사건마다 만든다
    op.create_table(
        'table_quests',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('hidden', 'active', 'succeeded', 'failed')", name=op.f('ck_table_quests_status_allowed')
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_quests_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_quests')),
    )


def downgrade() -> None:
    op.drop_table('table_quests')
