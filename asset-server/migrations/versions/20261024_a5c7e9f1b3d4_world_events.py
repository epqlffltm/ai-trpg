"""world events

Revision ID: a5c7e9f1b3d4
Revises: f4b6d8e0a2c3
Create Date: 2026-10-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a5c7e9f1b3d4'
down_revision: str | Sequence[str] | None = 'f4b6d8e0a2c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세계관의 이벤트(#591, 판의 형식 2). 있던 세계관은 빈 목록이다


def upgrade() -> None:
    op.add_column(
        'worlds', sa.Column('events', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('worlds', 'events')
