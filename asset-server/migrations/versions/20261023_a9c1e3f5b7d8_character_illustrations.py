"""character illustrations

Revision ID: a9c1e3f5b7d8
Revises: f8b0d2e4a6c7
Create Date: 2026-10-23 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a9c1e3f5b7d8'
down_revision: str | Sequence[str] | None = 'f8b0d2e4a6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 일러스트(그림, 해금 대상인지, 장면의 설명, 나오는 조건, #669). 있던 캐릭터는 일러스트가 없다(빈 목록)


def upgrade() -> None:
    op.add_column('characters', sa.Column('illustrations', postgresql.JSONB(), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('characters', 'illustrations')
