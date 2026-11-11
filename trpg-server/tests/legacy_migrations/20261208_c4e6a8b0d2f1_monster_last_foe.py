"""monster last foe

Revision ID: c4e6a8b0d2f1
Revises: e3bad76061cb
Create Date: 2026-12-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e6a8b0d2f1'
down_revision: str | Sequence[str] | None = 'e3bad76061cb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 쫓아오는 몬스터(#254). 마리마다 마지막으로 싸운 앉은 사람을 적는다. 흩어져 도망치면 그 사람을 쫓는다.
# 있던 마리는 비어 있다(다음에 싸우면 적힌다). 앉은 사람의 행에 외래 키를 걸지 않는다(나간 사람이어도 남는다).
# 되돌리면 그 기록을 잃는다. 쫓아와 옮겨진 마리는 옮겨진 자리에 그대로 있다


def upgrade() -> None:
    op.add_column('table_monsters', sa.Column('last_foe', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('table_monsters', 'last_foe')
