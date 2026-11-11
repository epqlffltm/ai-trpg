"""round time limit

Revision ID: a2c4e6f8b0d1
Revises: f1a3c5e7b9d0
Create Date: 2026-10-11 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a2c4e6f8b0d1'
down_revision: str | Sequence[str] | None = 'f1a3c5e7b9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 열린 라운드의 조건. 마감이 지난 라운드를 찾는 색인이 이 라운드만 담는다
OPEN_ROUND = 'closed_at IS NULL AND closing_at IS NULL'


def upgrade() -> None:
    # 테이블의 시간 제한(초). 있던 테이블은 비워 둔다. 그때처럼 시간 제한 없이 간다
    op.add_column('game_tables', sa.Column('round_time_limit', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_game_tables_round_time_limit_range'),
        'game_tables',
        'round_time_limit IS NULL OR round_time_limit BETWEEN 30 AND 3600',
    )
    # 라운드의 마감. 있던 라운드는 비워 둔다. 마감이 없다
    op.add_column('table_rounds', sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        'ix_table_rounds_open_deadline', 'table_rounds', ['deadline_at'], unique=False, postgresql_where=OPEN_ROUND
    )


def downgrade() -> None:
    op.drop_index('ix_table_rounds_open_deadline', table_name='table_rounds', postgresql_where=OPEN_ROUND)
    op.drop_column('table_rounds', 'deadline_at')
    op.drop_column('game_tables', 'round_time_limit')
