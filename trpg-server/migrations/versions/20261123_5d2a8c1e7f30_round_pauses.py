"""round pauses

Revision ID: 5d2a8c1e7f30
Revises: 278ff7b6359c
Create Date: 2026-11-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5d2a8c1e7f30'
down_revision: str | Sequence[str] | None = '278ff7b6359c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 아무도 선언하지 않은 라운드를 멈춘다(#1341).
#   - table_rounds.paused_at: 마감이 지났는데 아무도 선언하지 않아 멈춘 시각. 비어 있으면 멈추지 않았다
# 되돌리면 칸을 지운다. 멈춘 라운드는 마감이 없는 열린 라운드로 남는다(누가 내거나 방장이 닫으면 넘어간다)


def upgrade() -> None:
    op.add_column('table_rounds', sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('table_rounds', 'paused_at')
