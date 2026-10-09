"""round moves

Revision ID: c9e1f3a5b7d8
Revises: b8d0f2a4c6e7
Create Date: 2026-10-09 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c9e1f3a5b7d8'
down_revision: str | Sequence[str] | None = 'b8d0f2a4c6e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 있던 라운드는 비워 둔다.
    # 닫힌 라운드는 이 칸을 읽지 않는다. 닫는 중이던 라운드는 서술할 때 지금 앉은 사람들로 만든다(service.frozen_moves)
    op.add_column('table_rounds', sa.Column('moves', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('table_rounds', 'moves')
