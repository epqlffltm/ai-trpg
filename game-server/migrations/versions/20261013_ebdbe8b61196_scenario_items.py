"""scenario items

Revision ID: ebdbe8b61196
Revises: fc7641ab2503
Create Date: 2026-10-13 10:16:09.336984

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'ebdbe8b61196'
down_revision: str | Sequence[str] | None = 'fc7641ab2503'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 시나리오는 아이템 규칙도 시작 소지품도 없다(모든 물건 항목이 장비다)
    op.add_column(
        'scenarios',
        sa.Column(
            'items', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        'scenarios',
        sa.Column(
            'starting_items',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_items_count'), 'scenarios', 'jsonb_array_length(items) <= 100')
    op.create_check_constraint(
        op.f('ck_scenarios_starting_items_count'), 'scenarios', 'jsonb_array_length(starting_items) <= 20'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_starting_items_count'), 'scenarios', type_='check')
    op.drop_constraint(op.f('ck_scenarios_items_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'starting_items')
    op.drop_column('scenarios', 'items')
