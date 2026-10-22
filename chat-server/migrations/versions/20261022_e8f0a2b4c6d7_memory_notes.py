"""memory notes

Revision ID: e8f0a2b4c6d7
Revises: d7e9f1a3b5c6
Create Date: 2026-10-22 23:58:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e8f0a2b4c6d7'
down_revision: str | Sequence[str] | None = 'd7e9f1a3b5c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 기억 메모(app/memory/). 사용자가 보고 고치는 짧은 글. 대화를 지우면 함께 지워진다


def upgrade() -> None:
    op.create_table(
        'memory_notes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source IN ('user', 'summary')", name=op.f('ck_memory_notes_source_allowed')),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_memory_notes_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_memory_notes')),
    )
    op.create_index(op.f('ix_memory_notes_conversation_id'), 'memory_notes', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_memory_notes_conversation_id'), table_name='memory_notes')
    op.drop_table('memory_notes')
