"""suggestions

Revision ID: a4b6c8d0e2f3
Revises: f3a5b7c9d1e2
Create Date: 2026-10-22 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a4b6c8d0e2f3'
down_revision: str | Sequence[str] | None = 'f3a5b7c9d1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 다음 답 추천(app/conversation/suggestions.py). 말마다의 선택지. 있던 말은 빈 목록이다


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('suggestions', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_messages_suggestions_at_most_three'), 'messages', 'cardinality(suggestions) <= 3'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_messages_suggestions_at_most_three'), 'messages', type_='check')
    op.drop_column('messages', 'suggestions')
