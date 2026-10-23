"""message expression

Revision ID: e4f6a8b0c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-10-23 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e4f6a8b0c2d3'
down_revision: str | Sequence[str] | None = 'd3e5f7a9b1c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 답에서 모델이 고른 표정(app/conversation/expressions.py). 있던 답은 기본 표정이다(비어 있다)


def upgrade() -> None:
    op.add_column('messages', sa.Column('expression', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'expression')
