"""happenings

Revision ID: a4d8e2c6f1b3
Revises: e5b9c3a7d1f4
Create Date: 2026-10-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a4d8e2c6f1b3'
down_revision: str | Sequence[str] | None = 'e5b9c3a7d1f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 판의 사건 규칙(#367). 시나리오에 규칙을 적는 칸과, 테이블에서 일어난 사건을 적는 표다


def upgrade() -> None:
    op.create_table(
        'table_happenings',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('moves', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_happenings_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_happenings_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_happenings')),
    )
    # 있던 시나리오는 사건 규칙이 없다
    op.add_column(
        'scenarios',
        sa.Column(
            'happenings',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_happenings_count'), 'scenarios', 'jsonb_array_length(happenings) <= 50'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_happenings_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'happenings')
    op.drop_table('table_happenings')
