"""scenario quests

Revision ID: cd307cbf3323
Revises: 8a0d7f7760cc
Create Date: 2026-10-14 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'cd307cbf3323'
down_revision: str | Sequence[str] | None = '8a0d7f7760cc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 시나리오는 퀘스트 규칙이 없다(사건 항목은 모두 숨긴 채로 시작하는 퀘스트다)
    op.add_column(
        'scenarios',
        sa.Column(
            'quests', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_quests_count'), 'scenarios', 'jsonb_array_length(quests) <= 50')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_quests_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'quests')
