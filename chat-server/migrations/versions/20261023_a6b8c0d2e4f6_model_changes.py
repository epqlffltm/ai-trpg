"""model changes

Revision ID: a6b8c0d2e4f6
Revises: f5a7b9c1d3e4
Create Date: 2026-10-23 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a6b8c0d2e4f6'
down_revision: str | Sequence[str] | None = 'f5a7b9c1d3e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델이 제안해 서버가 받아들인 상태의 변화(#676). 답에는 칩으로 보일 변화를, 상태에는 이 가지에서 받은 물건을 둔다.
# 있던 답과 상태는 빈 목록이다


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )
    op.add_column(
        'message_states',
        sa.Column('received', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('message_states', 'received')
    op.drop_column('messages', 'changes')
