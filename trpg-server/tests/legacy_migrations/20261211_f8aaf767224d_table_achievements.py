"""table achievements

Revision ID: f8aaf767224d
Revises: f8dd2604a92d
Create Date: 2026-12-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f8aaf767224d'
down_revision: str | Sequence[str] | None = 'f8dd2604a92d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블 하나에서 받은 판의 업적(docs/architecture/achievements.md). 라운드가 닫힐 때 엔진이 준다.
# 테이블에서 업적 하나는 한 번이다(기본 키). 받은 사람들(user_ids)은 public_id 의 글자의 JSON 목록이다.
# 있던 테이블은 받은 업적이 없다. 다음에 닫히는 라운드부터 본다
# 되돌리면 테이블의 기록을 잃는다(계정의 기록 player_achievements 는 남는다)


def upgrade() -> None:
    op.create_table(
        'table_achievements',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('user_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_achievements_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_table_achievements_table_id_game_tables'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'achievement_id', name=op.f('pk_table_achievements')),
    )


def downgrade() -> None:
    op.drop_table('table_achievements')
