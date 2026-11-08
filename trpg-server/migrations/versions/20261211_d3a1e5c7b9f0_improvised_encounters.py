"""improvised encounters

Revision ID: d3a1e5c7b9f0
Revises: f8dd2604a92d
Create Date: 2026-11-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd3a1e5c7b9f0'
down_revision: str | Sequence[str] | None = 'f8dd2604a92d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 즉흥 조우(#254). 시나리오의 횟수(0 이면 꺼짐)와, 테이블이 받아들인 수다. 있던 것은 모두 0 이다(꺼져 있다).
# 상한은 모델과 같다(app/assets/models.py 의 IMPROVISED_ENCOUNTERS_MAX). 앱의 코드를 가져오지 않고 여기에 적어 둔다
RANGE = 'improvised_encounters BETWEEN 0 AND 20'


def upgrade() -> None:
    op.add_column(
        'scenarios', sa.Column('improvised_encounters', sa.SmallInteger(), server_default=sa.text('0'), nullable=False)
    )
    op.create_check_constraint(op.f('ck_scenarios_improvised_encounters_range'), 'scenarios', RANGE)
    op.add_column(
        'game_tables',
        sa.Column('improvised_encounters', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('game_tables', 'improvised_encounters')
    op.drop_constraint(op.f('ck_scenarios_improvised_encounters_range'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'improvised_encounters')
