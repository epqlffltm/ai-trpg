"""message states

Revision ID: c6d8e0f2a4b5
Revises: b5c7d9e1f3a4
Create Date: 2026-10-22 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c6d8e0f2a4b5'
down_revision: str | Sequence[str] | None = 'b5c7d9e1f3a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장소와 소지품(app/world/). 사람의 행동 말(role action)과, 상태가 바뀐 말마다의 상태


def upgrade() -> None:
    op.drop_constraint(op.f('ck_messages_role_allowed'), 'messages', type_='check')
    op.create_check_constraint(op.f('ck_messages_role_allowed'), 'messages', "role IN ('user', 'assistant', 'action')")
    op.create_table(
        'message_states',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('place', sa.String(length=40), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('inventory', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('visited', postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.CheckConstraint('minutes >= 0', name=op.f('ck_message_states_minutes_not_negative')),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_message_states_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_message_states')),
    )


def downgrade() -> None:
    op.drop_table('message_states')
    op.drop_constraint(op.f('ck_messages_role_allowed'), 'messages', type_='check')
    op.create_check_constraint(op.f('ck_messages_role_allowed'), 'messages', "role IN ('user', 'assistant')")
