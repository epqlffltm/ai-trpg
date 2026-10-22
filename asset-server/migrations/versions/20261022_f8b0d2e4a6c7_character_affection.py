"""character affection

Revision ID: f8b0d2e4a6c7
Revises: e7a9c1d3f5b6
Create Date: 2026-10-22 23:59:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f8b0d2e4a6c7'
down_revision: str | Sequence[str] | None = 'e7a9c1d3f5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙). 있던 캐릭터는 호감도가 없다(null)


def upgrade() -> None:
    op.add_column('characters', sa.Column('affection', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('characters', 'affection')
