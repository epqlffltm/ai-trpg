"""credit wait

Revision ID: 6f045de249da
Revises: 6d9258671115
Create Date: 2026-10-12 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6f045de249da'
down_revision: str | Sequence[str] | None = '6d9258671115'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 서술이 실패한 채 닫히지 않은 라운드라는 조건. 모델(app/rounds/models.py 의 FAILED_CONDITION)과 같은 글자다
FAILED_CONDITION = 'narration_failed_at IS NOT NULL AND closed_at IS NULL'


def upgrade() -> None:
    # 있던 테이블은 기본값이다(5분, 자동으로 빼기 켬)
    op.add_column(
        'game_tables',
        sa.Column('credit_wait_seconds', sa.Integer(), server_default=sa.text('300'), nullable=False),
    )
    op.add_column(
        'game_tables',
        sa.Column('remove_short_payers', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_game_tables_credit_wait_seconds_range'), 'game_tables', 'credit_wait_seconds BETWEEN 30 AND 3600'
    )
    op.create_index(
        'ix_table_rounds_failed',
        'table_rounds',
        ['narration_failed_at'],
        postgresql_where=sa.text(FAILED_CONDITION),
    )


def downgrade() -> None:
    op.drop_index('ix_table_rounds_failed', table_name='table_rounds', postgresql_where=sa.text(FAILED_CONDITION))
    op.drop_constraint(op.f('ck_game_tables_credit_wait_seconds_range'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'remove_short_payers')
    op.drop_column('game_tables', 'credit_wait_seconds')
