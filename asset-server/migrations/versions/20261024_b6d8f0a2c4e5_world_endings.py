"""world endings

Revision ID: b6d8f0a2c4e5
Revises: a5c7e9f1b3d4
Create Date: 2026-10-24 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b6d8f0a2c4e5'
down_revision: str | Sequence[str] | None = 'a5c7e9f1b3d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세계관의 엔딩(#591, 판의 형식 3). 있던 세계관은 빈 목록이다. 인물의 고백은 인물(cast)의 문서 안이라 칸이 없다


def upgrade() -> None:
    op.add_column(
        'worlds', sa.Column('endings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('worlds', 'endings')
