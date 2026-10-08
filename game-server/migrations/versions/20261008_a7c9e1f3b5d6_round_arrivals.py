"""round arrivals

Revision ID: a7c9e1f3b5d6
Revises: f6b8d0e2a4c5
Create Date: 2026-10-08 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a7c9e1f3b5d6'
down_revision: str | Sequence[str] | None = 'f6b8d0e2a4c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 있던 라운드는 새로 들어온 캐릭터가 없었던 것으로 채운다
    op.add_column(
        'table_rounds',
        sa.Column('arrivals', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('table_rounds', 'arrivals')
