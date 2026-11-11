"""round memories

Revision ID: f9b1d3e5a7c9
Revises: e8a0c2d4f6b8
Create Date: 2026-10-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'f9b1d3e5a7c9'
down_revision: str | Sequence[str] | None = 'e8a0c2d4f6b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 벡터의 타입만 이름을 바꿔 불러온다(자동 생성은 pgvector 를 import 하지 않는다).
    # pgvector 는 로어북의 벡터(c5e7a9b1d3f5)가 이미 켜져 있는지 확인했다.
    # 있던 AI 호출의 기록은 지난 일을 넣지 않은 것으로 둔다
    op.create_table(
        'round_memories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_round_memories_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_round_memories_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_round_memories')),
        sa.UniqueConstraint('table_id', 'model', 'round_number', name=op.f('uq_round_memories_table_id')),
    )
    op.add_column(
        'ai_invocations',
        sa.Column('memory_rounds', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('ai_invocations', 'memory_rounds')
    op.drop_table('round_memories')
