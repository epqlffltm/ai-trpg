"""friendly fire

Revision ID: a7c9e1b3d5f8
Revises: f6b8d0e2a4c6
Create Date: 2026-11-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c9e1b3d5f8'
down_revision: str | Sequence[str] | None = 'f6b8d0e2a4c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 앉은 사람끼리 해칠 수 있는 정도(#803). 테이블의 것(방장)과 자리의 것(본인이 받아들이는 정도)이다.
# 둘 다 끔(off)이 기본이다. 이미 있는 테이블과 자리도 끔이 된다. 전처럼 동료를 해치지 못한다.
# 앱의 코드를 가져오지 않는다

ALLOWED = "friendly_fire IN ('off', 'prank', 'full')"
TABLES = ('game_tables', 'table_members')


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column('friendly_fire', sa.String(length=20), server_default=sa.text("'off'"), nullable=False)
        )
        op.create_check_constraint(op.f(f'ck_{table}_friendly_fire_allowed'), table, ALLOWED)


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f'ck_{table}_friendly_fire_allowed'), table, type_='check')
        op.drop_column(table, 'friendly_fire')
