"""round turns

Revision ID: acdbc74c8dce
Revises: 94ecd216de9a
Create Date: 2026-10-15 11:01:30.814983

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'acdbc74c8dce'
down_revision: str | Sequence[str] | None = '94ecd216de9a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 라운드는 차례 없이(앉은 순서로) 판정했다. 빈 목록이다
    op.add_column(
        'table_rounds',
        sa.Column('turns', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('table_rounds', 'turns')
