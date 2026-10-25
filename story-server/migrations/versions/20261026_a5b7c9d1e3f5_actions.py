"""actions

Revision ID: a5b7c9d1e3f5
Revises: f4a6b8c0d2e3
Create Date: 2026-10-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a5b7c9d1e3f5'
down_revision: str | Sequence[str] | None = 'f4a6b8c0d2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 행동(app/turns/actions.py)과 계정의 기록(app/records/).
#   - messages.event_id, ending_id: 행동 말에서 그 행동 뒤에 열린 이벤트와 본 엔딩(판의 id)
#   - ending_records: 사람마다, 세계관마다, 엔딩마다 처음 본 것. 본 세션은 지워지면 비운다


def upgrade() -> None:
    op.create_table(
        'ending_records',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('world_source', sa.Uuid(), nullable=False),
        sa.Column('ending_id', sa.String(length=40), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_ending_records_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('owner_id', 'world_source', 'ending_id', name=op.f('pk_ending_records')),
    )
    op.add_column('messages', sa.Column('event_id', sa.String(length=40), nullable=True))
    op.add_column('messages', sa.Column('ending_id', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'ending_id')
    op.drop_column('messages', 'event_id')
    op.drop_table('ending_records')
