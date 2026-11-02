"""campaign runs

Revision ID: c6d8e0f2a4b6
Revises: b5c7d9e1f3a5
Create Date: 2026-11-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c6d8e0f2a4b6'
down_revision: str | Sequence[str] | None = 'b5c7d9e1f3a5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캠페인의 플레이(#481 B, docs/architecture/campaigns.md). 플레이(campaign_runs), 편마다의 테이블(campaign_tables),
# 넘길 것(campaign_carries), 편의 퀘스트 결과(campaign_quest_results)를 만든다. 값을 글자 그대로 적는다
POSITION_RANGE = '0 <= position AND position < 10'


def upgrade() -> None:
    op.create_table(
        'campaign_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('host_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(POSITION_RANGE, name=op.f('ck_campaign_runs_position_range')),
        sa.CheckConstraint("status IN ('playing', 'ended')", name=op.f('ck_campaign_runs_status_allowed')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_runs_campaign_id_campaigns'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['campaign_versions.id'],
            name=op.f('fk_campaign_runs_version_id_campaign_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_runs')),
    )
    op.create_index(op.f('ix_campaign_runs_campaign_id'), 'campaign_runs', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_campaign_runs_host_id'), 'campaign_runs', ['host_id'], unique=False)
    op.create_table(
        'campaign_tables',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(POSITION_RANGE, name=op.f('ck_campaign_tables_position_range')),
        sa.ForeignKeyConstraint(
            ['run_id'], ['campaign_runs.id'], name=op.f('fk_campaign_tables_run_id_campaign_runs'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_campaign_tables_table_id_game_tables'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_campaign_tables')),
        sa.UniqueConstraint('run_id', 'position', name='uq_campaign_tables_position'),
    )
    op.create_table(
        'campaign_carries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('carry', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(POSITION_RANGE, name=op.f('ck_campaign_carries_position_range')),
        sa.ForeignKeyConstraint(
            ['run_id'], ['campaign_runs.id'], name=op.f('fk_campaign_carries_run_id_campaign_runs'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_carries')),
        sa.UniqueConstraint('run_id', 'position', 'user_id', name='uq_campaign_carries_person'),
    )
    op.create_index(op.f('ix_campaign_carries_user_id'), 'campaign_carries', ['user_id'], unique=False)
    op.create_table(
        'campaign_quest_results',
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.CheckConstraint(POSITION_RANGE, name=op.f('ck_campaign_quest_results_position_range')),
        sa.CheckConstraint("result IN ('succeeded', 'failed')", name=op.f('ck_campaign_quest_results_result_allowed')),
        sa.ForeignKeyConstraint(
            ['run_id'],
            ['campaign_runs.id'],
            name=op.f('fk_campaign_quest_results_run_id_campaign_runs'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('run_id', 'position', 'entry_id', name=op.f('pk_campaign_quest_results')),
    )


def downgrade() -> None:
    op.drop_table('campaign_quest_results')
    op.drop_index(op.f('ix_campaign_carries_user_id'), table_name='campaign_carries')
    op.drop_table('campaign_carries')
    op.drop_table('campaign_tables')
    op.drop_index(op.f('ix_campaign_runs_host_id'), table_name='campaign_runs')
    op.drop_index(op.f('ix_campaign_runs_campaign_id'), table_name='campaign_runs')
    op.drop_table('campaign_runs')
