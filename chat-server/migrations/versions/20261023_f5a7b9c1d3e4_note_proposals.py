"""note proposals

Revision ID: f5a7b9c1d3e4
Revises: e4f6a8b0c2d3
Create Date: 2026-10-23 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f5a7b9c1d3e4'
down_revision: str | Sequence[str] | None = 'e4f6a8b0c2d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 요약이 제안한 기억 메모를 사람이 받아들인 시각(#677). 비어 있으면 아직 제안이다(모델에 가지 않는다).
# 있던 메모는 모두 사용자가 쓴 것이라 비어 있어도 그대로 모델에 간다


def upgrade() -> None:
    op.add_column('memory_notes', sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('memory_notes', 'accepted_at')
