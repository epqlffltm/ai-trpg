"""encounters

Revision ID: 4cf01d0802ce
Revises: faf095a05b3b
Create Date: 2026-10-15 06:03:53.577809

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '4cf01d0802ce'
down_revision: str | Sequence[str] | None = 'faf095a05b3b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'table_monsters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('monster_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.SmallInteger(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('max_hp', sa.SmallInteger(), nullable=False),
        sa.Column('hp', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'alive'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(status = 'alive') = (hp > 0)", name=op.f('ck_table_monsters_alive_when_hp')),
        sa.CheckConstraint("jsonb_typeof(abilities) = 'object'", name=op.f('ck_table_monsters_abilities_is_object')),
        sa.CheckConstraint("status IN ('alive', 'downed', 'dead')", name=op.f('ck_table_monsters_status_allowed')),
        sa.CheckConstraint('hp BETWEEN 0 AND max_hp', name=op.f('ck_table_monsters_hp_range')),
        sa.CheckConstraint('max_hp >= 1', name=op.f('ck_table_monsters_max_hp_positive')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_table_monsters_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_monsters_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_monsters')),
        sa.UniqueConstraint('table_id', 'monster_id', 'number', name=op.f('uq_table_monsters_table_id')),
    )
    # 있던 시나리오는 조우가 없다
    op.add_column(
        'scenarios',
        sa.Column(
            'encounters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_encounters_count'), 'scenarios', 'jsonb_array_length(encounters) <= 50'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_encounters_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'encounters')
    op.drop_table('table_monsters')
