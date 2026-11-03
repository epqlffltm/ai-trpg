"""banners

Revision ID: a5c7e9b1d3f6
Revises: e8f0a2b4c6d8
Create Date: 2026-11-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a5c7e9b1d3f6'
down_revision: str | Sequence[str] | None = 'e8f0a2b4c6d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'banners',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name=op.f('ck_banners_period_order')),
        sa.CheckConstraint('position >= 0 AND position <= 999', name=op.f('ck_banners_position_range')),
        sa.ForeignKeyConstraint(
            ['scenario_id'], ['scenarios.asset_id'], name=op.f('fk_banners_scenario_id_scenarios'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_banners')),
    )
    op.create_index(op.f('ix_banners_scenario_id'), 'banners', ['scenario_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_banners_scenario_id'), table_name='banners')
    op.drop_table('banners')
