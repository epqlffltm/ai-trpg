"""monster patrol leg

Revision ID: b8d4f0c2e6a3
Revises: a7c3e9b1d5f2
Create Date: 2026-12-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d4f0c2e6a3'
down_revision: str | Sequence[str] | None = 'a7c3e9b1d5f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 순찰하는 몬스터(#254). 마리마다 순찰에서 지금 향하는 곳의 차례를 적는다(0 은 처음 자리).
# 있던 마리는 0 이다(처음 자리로 향한다. 이미 처음 자리에 있으면 첫 장소로 넘어간다).
# 되돌리면 그 차례를 잃는다. 순찰해 옮겨진 마리는 옮겨진 자리에 그대로 있다


def upgrade() -> None:
    op.add_column(
        'table_monsters', sa.Column('patrol_leg', sa.SmallInteger(), server_default=sa.text('0'), nullable=False)
    )
    op.create_check_constraint(op.f('ck_table_monsters_patrol_leg_not_negative'), 'table_monsters', 'patrol_leg >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_monsters_patrol_leg_not_negative'), 'table_monsters', type_='check')
    op.drop_column('table_monsters', 'patrol_leg')
