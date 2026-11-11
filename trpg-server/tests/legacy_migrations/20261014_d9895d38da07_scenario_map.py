"""scenario map

Revision ID: d9895d38da07
Revises: d0ae2b47aaa9
Create Date: 2026-10-14 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd9895d38da07'
down_revision: str | Sequence[str] | None = 'd0ae2b47aaa9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 시나리오는 맵이 없다(시작 장소도 길도 없다)
    op.add_column('scenarios', sa.Column('start_place', sa.Uuid(), nullable=True))
    op.add_column(
        'scenarios',
        sa.Column(
            'routes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_routes_count'), 'scenarios', 'jsonb_array_length(routes) <= 200')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_routes_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'routes')
    op.drop_column('scenarios', 'start_place')
