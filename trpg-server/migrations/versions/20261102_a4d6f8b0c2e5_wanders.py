"""wanders

Revision ID: a4d6f8b0c2e5
Revises: f3c5e7a9b1d4
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a4d6f8b0c2e5'
down_revision: str | Sequence[str] | None = 'f3c5e7a9b1d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 무작위 조우 표(#283). 시나리오에 {place_id, times, chance, monsters} 의 목록을 둔다. 있던 시나리오는 표가 없다.
# 판은 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_56)


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'wanders',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_wanders_count'), 'scenarios', 'jsonb_array_length(wanders) <= 50')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_wanders_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'wanders')
