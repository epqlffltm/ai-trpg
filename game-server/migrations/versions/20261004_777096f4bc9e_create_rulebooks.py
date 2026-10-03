"""create rulebooks

Revision ID: 777096f4bc9e
Revises: 767f2ebb8306
Create Date: 2026-10-04 00:39:53.928589

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '777096f4bc9e'
down_revision: str | Sequence[str] | None = '767f2ebb8306'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# assets.type 에 넣을 수 있는 값. 이 마이그레이션의 앞과 뒤
TYPES_BEFORE = "type IN ('world')"
TYPES_AFTER = "type IN ('world', 'rulebook')"


def upgrade() -> None:
    op.create_table(
        'rulebooks',
        sa.Column('gm_guide', sa.Text(), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint('char_length(gm_guide) <= 4000', name=op.f('ck_rulebooks_gm_guide_length')),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_rulebooks_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_rulebooks')),
    )

    # 자산의 종류에 rulebook 을 추가한다. CHECK 는 고칠 수 없어서 지우고 다시 만든다.
    # Alembic 은 CHECK 의 변경을 알아채지 못한다. 이 부분은 손으로 적었다
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_AFTER)


def downgrade() -> None:
    op.drop_table('rulebooks')

    # 룰북의 공통 부분(assets 의 행)을 지운다. 남겨 두면 아래에서 제약을 되돌릴 때 걸린다
    op.execute("DELETE FROM assets WHERE type = 'rulebook'")
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_BEFORE)
