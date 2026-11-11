"""campaigns

Revision ID: b5c7d9e1f3a5
Revises: a4b6c8d0e2f4
Create Date: 2026-11-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b5c7d9e1f3a5'
down_revision: str | Sequence[str] | None = 'a4b6c8d0e2f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캠페인(#481 B, docs/architecture/campaigns.md).
# 캠페인의 내용(campaigns), 편(campaign_episodes), 판(campaign_versions)을 만든다.
# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
# assets.type 에 넣을 수 있는 값. 이 마이그레이션의 앞과 뒤
TYPES_BEFORE = "type IN ('world', 'rulebook', 'scenario', 'lorebook', 'bestiary')"
TYPES_AFTER = "type IN ('world', 'rulebook', 'scenario', 'lorebook', 'bestiary', 'campaign')"


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_campaigns_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_campaigns')),
    )
    op.create_table(
        'campaign_episodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=30), nullable=False),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_episodes_position_range')),
        sa.CheckConstraint('char_length(title) <= 30', name=op.f('ck_campaign_episodes_title_length')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_episodes_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_campaign_episodes_scenario_id_scenarios'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_episodes')),
        sa.UniqueConstraint('campaign_id', 'position', name='uq_campaign_episodes_position'),
        sa.UniqueConstraint('campaign_id', 'scenario_id', name='uq_campaign_episodes_scenario'),
    )
    op.create_index(op.f('ix_campaign_episodes_scenario_id'), 'campaign_episodes', ['scenario_id'], unique=False)
    op.create_table(
        'campaign_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(note) <= 500', name=op.f('ck_campaign_versions_note_length')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_campaign_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_versions_campaign_id_campaigns'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_versions')),
        sa.UniqueConstraint('campaign_id', 'number', name=op.f('uq_campaign_versions_campaign_id')),
    )

    # 자산의 종류에 campaign 을 더한다. Alembic 은 CHECK 의 변경을 알아채지 못한다. 이 부분은 손으로 적었다
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_AFTER)


def downgrade() -> None:
    op.drop_table('campaign_versions')
    op.drop_index(op.f('ix_campaign_episodes_scenario_id'), table_name='campaign_episodes')
    op.drop_table('campaign_episodes')
    op.drop_table('campaigns')

    # 캠페인의 공통 부분(assets 의 행)을 지운다. 남겨 두면 아래에서 제약을 되돌릴 때 걸린다
    op.execute("DELETE FROM assets WHERE type = 'campaign'")
    op.drop_constraint(op.f('ck_assets_type_allowed'), 'assets', type_='check')
    op.create_check_constraint(op.f('ck_assets_type_allowed'), 'assets', TYPES_BEFORE)
