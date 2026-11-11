"""route doors

Revision ID: d1a3c5e7f9b2
Revises: c9f1b3d5e7a0
Create Date: 2026-10-30 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd1a3c5e7f9b2'
down_revision: str | Sequence[str] | None = 'c9f1b3d5e7a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 길의 문(#281). 자물쇠에 더해 빗장이 걸렸는지와 문이 부서졌는지를 적는다.
# 부서진 문은 열린 채다. 엔진의 실수를 DB 가 한 번 더 막는다


def upgrade() -> None:
    # 있던 문은 빗장이 없고 부서지지 않았다
    op.add_column(
        'table_route_locks', sa.Column('barred', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'table_route_locks', sa.Column('broken', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_table_route_locks_broken_is_open'), 'table_route_locks', 'NOT broken OR (NOT locked AND NOT barred)'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_route_locks_broken_is_open'), 'table_route_locks', type_='check')
    op.drop_column('table_route_locks', 'broken')
    op.drop_column('table_route_locks', 'barred')
