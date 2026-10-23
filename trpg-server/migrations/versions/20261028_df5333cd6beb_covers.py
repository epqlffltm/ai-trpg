"""covers

Revision ID: df5333cd6beb
Revises: b8e0a2c4d6f9
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'df5333cd6beb'
down_revision: str | Sequence[str] | None = 'b8e0a2c4d6f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 커버 세이브(#276). 시나리오에 장소마다의 커버({place_id, cover})를 둔다. 있던 시나리오는 커버가 없다.
# 판은 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_50)


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'covers',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_covers_count'), 'scenarios', 'jsonb_array_length(covers) <= 100')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_covers_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'covers')
