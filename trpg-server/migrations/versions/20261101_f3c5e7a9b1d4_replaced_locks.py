"""replaced locks

Revision ID: f3c5e7a9b1d4
Revises: e2b4d6f8a1c3
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3c5e7a9b1d4'
down_revision: str | Sequence[str] | None = 'e2b4d6f8a1c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 길의 문의 자물쇠를 바꾼다(#281). 바꿔 단 자물쇠 물건을 적는다.
# 자물쇠 물건 하나는 한 테이블에서 한 문에만 단다


def upgrade() -> None:
    # 있던 문은 자물쇠를 바꾸지 않았다
    op.add_column('table_route_locks', sa.Column('lock_item', sa.Uuid(), nullable=True))
    op.create_unique_constraint(op.f('uq_table_route_locks_table_id'), 'table_route_locks', ['table_id', 'lock_item'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_table_route_locks_table_id'), 'table_route_locks', type_='unique')
    op.drop_column('table_route_locks', 'lock_item')
