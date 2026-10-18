"""place items

Revision ID: ae3a917a8ac0
Revises: faee8694431a
Create Date: 2026-10-19 02:07:06.297921

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'ae3a917a8ac0'
down_revision: str | Sequence[str] | None = 'faee8694431a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'table_place_items',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.Column('hidden', sa.Boolean(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_place_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_place_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_place_items_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'slot', name=op.f('pk_table_place_items')),
    )
    # 있던 시나리오는 놓인 물건이 없다
    op.add_column(
        'scenarios',
        sa.Column(
            'place_items',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_place_items_count'), 'scenarios', 'jsonb_array_length(place_items) <= 100'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_place_items_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'place_items')
    op.drop_table('table_place_items')
