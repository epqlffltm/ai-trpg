"""create lorebooks

Revision ID: 20481772a0b3
Revises: 330a2688820f
Create Date: 2026-10-04 09:04:26.911615

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20481772a0b3'
down_revision: str | Sequence[str] | None = '330a2688820f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# assets.type 에 넣을 수 있는 값. 이 마이그레이션의 앞과 뒤
TYPES_BEFORE = "type IN ('world', 'rulebook', 'scenario')"
TYPES_AFTER = "type IN ('world', 'rulebook', 'scenario', 'lorebook')"


def upgrade() -> None:
    op.create_table(
        'lorebooks',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_lorebooks_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_lorebooks')),
    )
    op.create_table(
        'lore_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('keywords', postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cardinality(keywords) <= 5', name=op.f('ck_lore_entries_keywords_count')),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_lore_entries_content_length')),
        sa.ForeignKeyConstraint(
            ['lorebook_id'],
            ['lorebooks.asset_id'],
            name=op.f('fk_lore_entries_lorebook_id_lorebooks'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_entries')),
    )
    op.create_index(op.f('ix_lore_entries_lorebook_id'), 'lore_entries', ['lorebook_id'], unique=False)

    # 자산의 종류에 lorebook 을 추가한다. Alembic 은 CHECK 의 변경을 알아채지 못한다. 이 부분은 손으로 적었다
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_AFTER)


def downgrade() -> None:
    op.drop_index(op.f('ix_lore_entries_lorebook_id'), table_name='lore_entries')
    op.drop_table('lore_entries')
    op.drop_table('lorebooks')

    # 로어북의 공통 부분(assets 의 행)을 지운다. 남겨 두면 아래에서 제약을 되돌릴 때 걸린다
    op.execute("DELETE FROM assets WHERE type = 'lorebook'")
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_BEFORE)
