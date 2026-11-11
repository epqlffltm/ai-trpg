"""scenario submaps

Revision ID: fc73676e9587
Revises: c4e6a8b0d2f1
Create Date: 2026-12-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'fc73676e9587'
down_revision: str | Sequence[str] | None = 'c4e6a8b0d2f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장소가 품은 하위 맵(#284). 시나리오에 {place_id, places} 의 목록을 둔다. 마을 안의 건물, 건물의 층이다.
# 있던 시나리오는 하위 맵이 없다(빈 목록). 굳힌 판은 고치지 않는다.
# 판의 submaps 는 비워도 되는 칸이라 없으면 빈 목록이다.
# 되돌리면 하위 맵을 잃는다(맵의 장소와 길은 그대로다)


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'submaps',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(op.f('ck_scenarios_submaps_count'), 'scenarios', 'jsonb_array_length(submaps) <= 50')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_submaps_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'submaps')
