"""preset traps

Revision ID: f9b1d3e5a7c0
Revises: e8a0c2d4f6b9
Create Date: 2026-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f9b1d3e5a7c0'
down_revision: str | Sequence[str] | None = 'e8a0c2d4f6b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 미리 놓인 덫(#806 ②). 시나리오에 덫({place_id, entry_id, known})을 둔다. 있던 시나리오는 덫이 없다.
# 판의 칸(traps)은 비워도 되는 칸이라 굳힌 판을 고치지 않는다.
# 되돌리면 시나리오의 칸을 지운다.
# 이미 시작한 테이블에 놓인 덫(table_traps, 놓은 사람 없음)은 그 전 모양에도 들어가 그대로 둔다


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'traps',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_traps_count'), 'scenarios', 'jsonb_array_length(traps) <= 50')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_traps_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'traps')
