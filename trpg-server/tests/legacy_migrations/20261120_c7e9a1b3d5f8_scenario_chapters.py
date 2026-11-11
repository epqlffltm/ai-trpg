"""scenario chapters

Revision ID: c7e9a1b3d5f8
Revises: d1d345adf142
Create Date: 2026-11-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7e9a1b3d5f8'
down_revision: str | Sequence[str] | None = 'd1d345adf142'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장(#481, docs/architecture/chapters.md). 시나리오에 장({id, name, when, match, opens})을 둔다.
# 있던 시나리오는 장이 없다.
# 판의 칸(chapters)은 비워도 되는 칸이라 굳힌 판을 고치지 않는다.
# 되돌리면 시나리오의 칸을 지운다


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'chapters',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_chapters_count'), 'scenarios', 'jsonb_array_length(chapters) <= 20')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_chapters_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'chapters')
