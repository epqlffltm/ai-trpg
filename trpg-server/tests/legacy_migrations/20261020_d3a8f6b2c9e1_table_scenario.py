"""table scenario

Revision ID: d3a8f6b2c9e1
Revises: c7d2e9a4f1b6
Create Date: 2026-10-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd3a8f6b2c9e1'
down_revision: str | Sequence[str] | None = 'c7d2e9a4f1b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 테이블의 시나리오(#428). 이미 있는 테이블은 그 판의 시나리오로 채운 뒤 비울 수 없게 한다
    op.add_column('game_tables', sa.Column('scenario_id', sa.Uuid(), nullable=True))
    op.execute(
        'UPDATE game_tables SET scenario_id = scenario_versions.scenario_id '
        'FROM scenario_versions WHERE scenario_versions.id = game_tables.version_id'
    )
    op.alter_column('game_tables', 'scenario_id', nullable=False)
    op.create_foreign_key(
        op.f('fk_game_tables_scenario_id_scenarios'),
        'game_tables',
        'scenarios',
        ['scenario_id'],
        ['asset_id'],
        ondelete='RESTRICT',
    )
    # 로비가 시나리오로 거를 때 쓴다. 판을 잇지 않고 테이블에서 바로 거른다
    op.create_index(op.f('ix_game_tables_scenario_id'), 'game_tables', ['scenario_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_game_tables_scenario_id'), table_name='game_tables')
    op.drop_constraint(op.f('fk_game_tables_scenario_id_scenarios'), 'game_tables', type_='foreignkey')
    op.drop_column('game_tables', 'scenario_id')
