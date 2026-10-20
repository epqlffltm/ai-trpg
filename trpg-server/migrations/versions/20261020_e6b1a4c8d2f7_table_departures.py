"""table departures

Revision ID: e6b1a4c8d2f7
Revises: d3a8f6b2c9e1
Create Date: 2026-10-20 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e6b1a4c8d2f7'
down_revision: str | Sequence[str] | None = 'd3a8f6b2c9e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 떠난 사람(#428). 시작한 테이블에서 떠난 사람이 떠난 때까지의 기록을 읽게 한다(app/tables/past.py).
# 이미 떠난 사람은 채우지 않는다. 자리가 지워져서 누가 앉았었는지 알 수 없다.
# 되돌리면 떠난 사람들이 기록을 더 읽지 못한다. 개발용 DB 에서만 되돌린다


def upgrade() -> None:
    op.create_table(
        'table_departures',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('last_sequence', sa.Integer(), nullable=False),
        sa.Column('left_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('left', 'kicked', 'dropped')", name=op.f('ck_table_departures_kind_allowed')),
        sa.CheckConstraint('last_sequence >= 1', name=op.f('ck_table_departures_last_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_departures_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_table_departures')),
    )
    op.create_index('ix_table_departures_user_id_left_at', 'table_departures', ['user_id', 'left_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_table_departures_user_id_left_at', table_name='table_departures')
    op.drop_table('table_departures')
