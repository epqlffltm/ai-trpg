"""memory notes

Revision ID: a1b3c5d7e9f1
Revises: f0a2b4c6d8e0
Create Date: 2026-10-28 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b3c5d7e9f1'
down_revision: str | Sequence[str] | None = 'f0a2b4c6d8e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 기억 메모(app/memory/models.py). 세션마다의 짧은 글이고 세션을 지우면 함께 지워진다


def upgrade() -> None:
    op.create_table(
        'memory_notes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
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
