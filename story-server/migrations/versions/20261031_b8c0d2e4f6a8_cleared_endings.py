"""cleared endings

Revision ID: b8c0d2e4f6a8
Revises: a7b9c1d3e5f7
Create Date: 2026-10-31 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8c0d2e4f6a8'
down_revision: str | Sequence[str] | None = 'a7b9c1d3e5f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 회차 혜택(조건의 ending_seen). 세션을 시작할 때 그 사람이 그 세계관에서 본 엔딩들을 굳혀 둔다.
# 있던 세션은 빈 목록이다(그 세션의 판에는 그 조건이 없다)


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('cleared_endings', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'cleared_endings')
