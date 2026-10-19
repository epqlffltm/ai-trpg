"""table clocks

Revision ID: ed3db516b4b6
Revises: 8392922e1b1d, acdbc74c8dce
Create Date: 2026-10-15 11:41:05.811188

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'ed3db516b4b6'
# 두 갈래를 여기서 하나로 모은다. 판의 시계(8392922e1b1d)와 라운드의 차례(acdbc74c8dce)가 같은 앞(94ecd216de9a)에서
# 따로 나와 머지되어 head 가 둘이 되었다. 이미 머지한 두 파일은 고치지 않는다(어느 쪽을 먼저 올린 DB 도 그대로 올라온다)
down_revision: str | Sequence[str] | None = ('8392922e1b1d', 'acdbc74c8dce')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 다음 걸음의 한도. 모델(app/assets/models.py 의 ROUND_MAX_MINUTES)과 같은 값이다. 마이그레이션은 앱을 불러오지 않는다
ROUND_MAX_MINUTES = 7 * 24 * 60

# 있는 테이블마다 시계를 하나 단다. 판의 시작 시각으로(app/calendar/clock.py 의 start_minutes 와 같은 셈).
# 시계가 없던 옛 판(형식 24 보다 앞)은 1일째 8시다(DEFAULT_START_DAY, DEFAULT_START_HOUR).
# 이미 진행 중인 테이블도 시작 시각에서 시작한다. 그동안 흐른 시간은 셀 수 없다(라운드마다의 걸음이 없었다)
BACKFILL = """
INSERT INTO table_clocks (table_id, minutes)
SELECT id,
       ((COALESCE((content -> 'clock' ->> 'start_day')::int, 1) - 1) * 24
        + COALESCE((content -> 'clock' ->> 'start_hour')::int, 8)) * 60
FROM game_tables
"""


def upgrade() -> None:
    op.create_table(
        'table_clocks',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('next_step_minutes', sa.Integer(), nullable=True),
        sa.CheckConstraint('minutes >= 0', name=op.f('ck_table_clocks_minutes_not_negative')),
        sa.CheckConstraint(
            f'next_step_minutes BETWEEN 0 AND {ROUND_MAX_MINUTES}', name=op.f('ck_table_clocks_next_step_range')
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_clocks_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_table_clocks')),
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_table('table_clocks')
