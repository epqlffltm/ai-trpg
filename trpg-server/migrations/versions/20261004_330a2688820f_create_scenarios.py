"""create scenarios

Revision ID: 330a2688820f
Revises: 777096f4bc9e
Create Date: 2026-10-04 01:19:28.478026

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '330a2688820f'
down_revision: str | Sequence[str] | None = '777096f4bc9e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# assets.type 에 넣을 수 있는 값. 이 마이그레이션의 앞과 뒤
TYPES_BEFORE = "type IN ('world', 'rulebook')"
TYPES_AFTER = "type IN ('world', 'rulebook', 'scenario')"


def upgrade() -> None:
    op.create_table(
        'scenarios',
        sa.Column('rulebook_id', sa.Uuid(), nullable=True),
        sa.Column('world_id', sa.Uuid(), nullable=True),
        sa.Column('opening', sa.Text(), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint('char_length(opening) <= 2000', name=op.f('ck_scenarios_opening_length')),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_scenarios_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['rulebook_id'],
            ['rulebooks.asset_id'],
            name=op.f('fk_scenarios_rulebook_id_rulebooks'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.asset_id'], name=op.f('fk_scenarios_world_id_worlds'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_scenarios')),
    )
    op.create_index(op.f('ix_scenarios_rulebook_id'), 'scenarios', ['rulebook_id'], unique=False)
    op.create_index(op.f('ix_scenarios_world_id'), 'scenarios', ['world_id'], unique=False)

    # 자산의 종류에 scenario 를 추가한다. Alembic 은 CHECK 의 변경을 알아채지 못한다. 이 부분은 손으로 적었다
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_AFTER)


def downgrade() -> None:
    op.drop_index(op.f('ix_scenarios_world_id'), table_name='scenarios')
    op.drop_index(op.f('ix_scenarios_rulebook_id'), table_name='scenarios')
    op.drop_table('scenarios')

    # 시나리오의 공통 부분(assets 의 행)을 지운다. 남겨 두면 아래에서 제약을 되돌릴 때 걸린다
    op.execute("DELETE FROM assets WHERE type = 'scenario'")
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_BEFORE)
