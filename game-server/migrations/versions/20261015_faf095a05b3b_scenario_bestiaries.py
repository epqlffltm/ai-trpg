"""scenario bestiaries

Revision ID: faf095a05b3b
Revises: 4a3f01eb5b37
Create Date: 2026-10-15 05:31:32.704364

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'faf095a05b3b'
down_revision: str | Sequence[str] | None = '4a3f01eb5b37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'scenario_bestiaries',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('bestiary_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['bestiary_id'],
            ['bestiaries.asset_id'],
            name=op.f('fk_scenario_bestiaries_bestiary_id_bestiaries'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_bestiaries_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('scenario_id', 'bestiary_id', name=op.f('pk_scenario_bestiaries')),
    )
    op.create_index(op.f('ix_scenario_bestiaries_bestiary_id'), 'scenario_bestiaries', ['bestiary_id'], unique=False)

    # 있던 시나리오는 몬스터 시트가 없다
    op.add_column(
        'scenarios',
        sa.Column(
            'monster_sheets',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_monster_sheets_count'), 'scenarios', 'jsonb_array_length(monster_sheets) <= 100'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_monster_sheets_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'monster_sheets')
    op.drop_index(op.f('ix_scenario_bestiaries_bestiary_id'), table_name='scenario_bestiaries')
    op.drop_table('scenario_bestiaries')
