"""affection state

Revision ID: a0b2c4d6e8f9
Revises: f9a1b3c5d7e8
Create Date: 2026-10-23 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a0b2c4d6e8f9'
down_revision: str | Sequence[str] | None = 'f9a1b3c5d7e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 호감도(app/world/affection.py). 말마다의 상태에 호감도와 걸린 "처음 한 번만" 규칙을 더한다.
# 있던 상태는 호감도가 없다(null). 판에 호감도가 있으면 읽을 때 시작 값으로 본다(app/world/state.py 의 filled)


def upgrade() -> None:
    op.add_column('message_states', sa.Column('affection', sa.Integer(), nullable=True))
    op.add_column(
        'message_states',
        sa.Column('fired', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_message_states_affection_in_range'),
        'message_states',
        'affection IS NULL OR affection BETWEEN 0 AND 100',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_message_states_affection_in_range'), 'message_states', type_='check')
    op.drop_column('message_states', 'fired')
    op.drop_column('message_states', 'affection')
