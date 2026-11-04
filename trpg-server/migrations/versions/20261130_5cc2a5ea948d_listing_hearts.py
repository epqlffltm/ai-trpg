"""listing_hearts

시나리오의 관심(하트, #989). 한 사람이 시나리오 하나에 한 번 둔다. 공개 정보에 관심의 수를 적어 둔다.

Revision ID: 5cc2a5ea948d
Revises: a5c7e9b1d3f6
Create Date: 2026-11-30 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5cc2a5ea948d'
down_revision: str | Sequence[str] | None = 'a5c7e9b1d3f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'listing_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['listings.scenario_id'],
            name=op.f('fk_listing_hearts_scenario_id_listings'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', 'scenario_id', name=op.f('pk_listing_hearts')),
    )
    op.create_index(op.f('ix_listing_hearts_scenario_id'), 'listing_hearts', ['scenario_id'], unique=False)
    op.create_index('ix_listing_hearts_user_created', 'listing_hearts', ['user_id', 'created_at'], unique=False)
    op.add_column('listings', sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_listings_heart_count_not_negative'), 'listings', 'heart_count >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_listings_heart_count_not_negative'), 'listings', type_='check')
    op.drop_column('listings', 'heart_count')
    op.drop_index('ix_listing_hearts_user_created', table_name='listing_hearts')
    op.drop_index(op.f('ix_listing_hearts_scenario_id'), table_name='listing_hearts')
    op.drop_table('listing_hearts')
