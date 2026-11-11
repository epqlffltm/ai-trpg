"""campaign seats

Revision ID: d7e9f1a3b5c7
Revises: c6d8e0f2a4b6
Create Date: 2026-11-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd7e9f1a3b5c7'
down_revision: str | Sequence[str] | None = 'c6d8e0f2a4b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캠페인(#481 B)의 다음 편에서 넘긴 캐릭터로 앉은 자리(campaign_seats). 테이블과 사람, 그 자리가 쓰는 넘길 것


def upgrade() -> None:
    op.create_table(
        'campaign_seats',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('carry_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['carry_id'],
            ['campaign_carries.id'],
            name=op.f('fk_campaign_seats_carry_id_campaign_carries'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_campaign_seats_table_id_game_tables'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_campaign_seats')),
    )
    op.create_index(op.f('ix_campaign_seats_carry_id'), 'campaign_seats', ['carry_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_campaign_seats_carry_id'), table_name='campaign_seats')
    op.drop_table('campaign_seats')
