"""message chapters

Revision ID: c9d1e3f5a7b9
Revises: b8c0d2e4f6a8
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d1e3f5a7b9'
down_revision: str | Sequence[str] | None = 'b8c0d2e4f6a8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장(docs/architecture/chapters.md). 행동 말에 그 행동으로 넘어간 장을 적는다.
# 있던 말은 비어 있다(그 판에는 장이 없다). 지금 장은 말에 붙은 상태(message_states 의 JSON)에 든다


def upgrade() -> None:
    op.add_column('messages', sa.Column('chapter_id', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'chapter_id')
