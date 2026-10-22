"""outfit

Revision ID: d7e9f1a3b5c6
Revises: c6d8e0f2a4b5
Create Date: 2026-10-22 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd7e9f1a3b5c6'
down_revision: str | Sequence[str] | None = 'c6d8e0f2a4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 상대의 차림. 사용자가 건넨 옷을 상대가 입는다. 있던 상태는 아무것도 입지 않은 것이다


def upgrade() -> None:
    op.add_column(
        'message_states',
        sa.Column('outfit', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('message_states', 'outfit')
