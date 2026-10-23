"""conversation start hour

Revision ID: b1c3d5e7f9a0
Revises: a0b2c4d6e8f9
Create Date: 2026-10-23 00:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b1c3d5e7f9a0'
down_revision: str | Sequence[str] | None = 'a0b2c4d6e8f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 대화의 시작 시각(1일째 몇 시, #668). 고른 시작 상황의 hour 를 복사해 둔다.
# 있던 대화는 정오에 시작한 것으로 본다(asset 서버의 형식 3 까지의 판과 같다)


def upgrade() -> None:
    op.add_column('conversations', sa.Column('start_hour', sa.SmallInteger(), server_default='12', nullable=False))
    op.create_check_constraint(
        op.f('ck_conversations_start_hour_in_day'), 'conversations', 'start_hour BETWEEN 0 AND 23'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_conversations_start_hour_in_day'), 'conversations', type_='check')
    op.drop_column('conversations', 'start_hour')
