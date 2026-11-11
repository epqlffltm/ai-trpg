"""turn order

Revision ID: c9e5a1d3f7b4
Revises: b8d4f0c2e6a3
Create Date: 2026-12-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c9e5a1d3f7b4'
down_revision: str | Sequence[str] | None = 'b8d4f0c2e6a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 차례대로 진행하는 방식(#287).
#   - game_tables: 진행 방식(turn_mode, 기본 together), 지금 바퀴(turn_cycle), 남은 차례(turn_queue), 지난 차례의
#     기다리기(turn_waits). 있던 테이블은 한꺼번에 진행하고 바퀴는 0, 둘은 빈 목록이다
#   - table_rounds: 게임 안의 라운드(cycle)와 차례의 주인(actor_id). 있던 라운드는 cycle = number, 주인은 없다
# 되돌리면 칸을 지운다. 차례대로 진행하던 테이블은 한꺼번에 진행하는 것으로 남는다


def upgrade() -> None:
    op.add_column(
        'game_tables',
        sa.Column('turn_mode', sa.String(length=20), server_default=sa.text("'together'"), nullable=False),
    )
    op.add_column('game_tables', sa.Column('turn_cycle', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column(
        'game_tables',
        sa.Column(
            'turn_queue', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        'game_tables',
        sa.Column(
            'turn_waits', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f('ck_game_tables_turn_mode_allowed'), 'game_tables', "turn_mode IN ('together', 'turns')"
    )
    op.create_check_constraint(op.f('ck_game_tables_turn_cycle_not_negative'), 'game_tables', 'turn_cycle >= 0')
    op.create_check_constraint(
        op.f('ck_game_tables_turn_queue_is_array'), 'game_tables', "jsonb_typeof(turn_queue) = 'array'"
    )
    op.create_check_constraint(
        op.f('ck_game_tables_turn_waits_is_array'), 'game_tables', "jsonb_typeof(turn_waits) = 'array'"
    )
    op.add_column('table_rounds', sa.Column('cycle', sa.Integer(), nullable=True))
    op.execute('UPDATE table_rounds SET cycle = number')
    op.alter_column('table_rounds', 'cycle', nullable=False)
    op.create_check_constraint(op.f('ck_table_rounds_cycle_positive'), 'table_rounds', 'cycle >= 1')
    op.add_column('table_rounds', sa.Column('actor_id', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('table_rounds', 'actor_id')
    op.drop_constraint(op.f('ck_table_rounds_cycle_positive'), 'table_rounds', type_='check')
    op.drop_column('table_rounds', 'cycle')
    for name in ('turn_waits_is_array', 'turn_queue_is_array', 'turn_cycle_not_negative', 'turn_mode_allowed'):
        op.drop_constraint(op.f(f'ck_game_tables_{name}'), 'game_tables', type_='check')
    for column in ('turn_waits', 'turn_queue', 'turn_cycle', 'turn_mode'):
        op.drop_column('game_tables', column)
