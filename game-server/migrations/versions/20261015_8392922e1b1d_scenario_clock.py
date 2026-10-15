"""scenario clock

Revision ID: 8392922e1b1d
Revises: 94ecd216de9a
Create Date: 2026-10-15 11:09:11.527064

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8392922e1b1d'
down_revision: str | Sequence[str] | None = '94ecd216de9a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 조건의 상한. 이 마이그레이션을 만들 때의 값이다(app/assets/models.py 의 CLOCK_MAX_DAY, ROUND_MAX_MINUTES).
# 앱의 코드를 가져오지 않고 여기에 적어 둔다. 나중에 상한을 바꾸면 새 마이그레이션을 만든다
CLOCK_MAX_DAY = 999
ROUND_MAX_MINUTES = 7 * 24 * 60


def upgrade() -> None:
    # 있던 시나리오는 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다. 새 시나리오의 기본값과 같다.
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.add_column('scenarios', sa.Column('start_day', sa.SmallInteger(), server_default=sa.text('1'), nullable=False))
    op.add_column('scenarios', sa.Column('start_hour', sa.SmallInteger(), server_default=sa.text('8'), nullable=False))
    op.add_column('scenarios', sa.Column('round_minutes', sa.Integer(), server_default=sa.text('10'), nullable=False))
    op.create_check_constraint(
        op.f('ck_scenarios_start_day_range'), 'scenarios', f'start_day BETWEEN 1 AND {CLOCK_MAX_DAY}'
    )
    op.create_check_constraint(op.f('ck_scenarios_start_hour_range'), 'scenarios', 'start_hour BETWEEN 0 AND 23')
    op.create_check_constraint(
        op.f('ck_scenarios_round_minutes_range'), 'scenarios', f'round_minutes BETWEEN 1 AND {ROUND_MAX_MINUTES}'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_round_minutes_range'), 'scenarios', type_='check')
    op.drop_constraint(op.f('ck_scenarios_start_hour_range'), 'scenarios', type_='check')
    op.drop_constraint(op.f('ck_scenarios_start_day_range'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'round_minutes')
    op.drop_column('scenarios', 'start_hour')
    op.drop_column('scenarios', 'start_day')
