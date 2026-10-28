"""note proposals

Revision ID: c3d5e7f9a1b3
Revises: b2c4d6e8f0a2
Create Date: 2026-10-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d5e7f9a1b3'
down_revision: str | Sequence[str] | None = 'b2c4d6e8f0a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 요약이 제안하는 기억 메모(app/memory/models.py, chat 의 #677 과 같다).
#   - source: 누가 썼는가(user, summary). 지금까지의 메모는 사용자가 쓴 것이다(user)
#   - accepted_at: 요약의 제안을 사람이 받아들인 시각. 비어 있는 제안은 모델에 가지 않는다


def upgrade() -> None:
    op.add_column('memory_notes', sa.Column('source', sa.String(length=10), server_default='user', nullable=False))
    op.add_column('memory_notes', sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f('ck_memory_notes_source_allowed'), 'memory_notes', "source IN ('user', 'summary')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_memory_notes_source_allowed'), 'memory_notes', type_='check')
    op.drop_column('memory_notes', 'accepted_at')
    op.drop_column('memory_notes', 'source')
