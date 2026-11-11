"""monster home place

Revision ID: a7c3e9b1d5f2
Revises: bbf9dad39cec
Create Date: 2026-12-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c3e9b1d5f2'
down_revision: str | Sequence[str] | None = 'bbf9dad39cec'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 배회하는 몬스터(#254). 마리마다 처음 놓인 자리를 적는다. 배회는 그 자리에서 길의 칸 수의 한도 안에서만 움직인다.
# 있던 마리는 지금 있는 곳을 처음 자리로 채운다(쫓아와 옮겨진 마리는 옮겨진 자리가 처음 자리가 된다).
# 되돌리면 그 기록을 잃는다. 배회해 옮겨진 마리는 옮겨진 자리에 그대로 있다


def upgrade() -> None:
    op.add_column('table_monsters', sa.Column('home_place_id', sa.Uuid(), nullable=True))
    op.execute('UPDATE table_monsters SET home_place_id = place_id')
    op.alter_column('table_monsters', 'home_place_id', nullable=False)


def downgrade() -> None:
    op.drop_column('table_monsters', 'home_place_id')
