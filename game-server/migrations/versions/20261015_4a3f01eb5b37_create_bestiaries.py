"""create bestiaries

Revision ID: 4a3f01eb5b37
Revises: 3e8b6d1c5a47
Create Date: 2026-10-15 03:28:27.713923

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4a3f01eb5b37'
down_revision: str | Sequence[str] | None = '3e8b6d1c5a47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
# assets.type 에 넣을 수 있는 값. 이 마이그레이션의 앞과 뒤
TYPES_BEFORE = "type IN ('world', 'rulebook', 'scenario', 'lorebook')"
TYPES_AFTER = "type IN ('world', 'rulebook', 'scenario', 'lorebook', 'bestiary')"
# 몬스터의 타입
KINDS = "'humanoid', 'beast', 'undead', 'construct', 'other'"


def upgrade() -> None:
    op.create_table(
        'bestiaries',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_bestiaries_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_bestiaries')),
    )
    op.create_table(
        'monsters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('bestiary_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f'kind IN ({KINDS})', name=op.f('ck_monsters_kind_allowed')),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_monsters_content_length')),
        sa.ForeignKeyConstraint(
            ['bestiary_id'],
            ['bestiaries.asset_id'],
            name=op.f('fk_monsters_bestiary_id_bestiaries'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_monsters')),
    )
    op.create_index(op.f('ix_monsters_bestiary_id'), 'monsters', ['bestiary_id'], unique=False)

    # 자산의 종류에 bestiary 를 더한다. Alembic 은 CHECK 의 변경을 알아채지 못한다. 이 부분은 손으로 적었다
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_AFTER)


def downgrade() -> None:
    op.drop_index(op.f('ix_monsters_bestiary_id'), table_name='monsters')
    op.drop_table('monsters')
    op.drop_table('bestiaries')

    # 도감의 공통 부분(assets 의 행)을 지운다. 남겨 두면 아래에서 제약을 되돌릴 때 걸린다
    op.execute("DELETE FROM assets WHERE type = 'bestiary'")
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_BEFORE)
