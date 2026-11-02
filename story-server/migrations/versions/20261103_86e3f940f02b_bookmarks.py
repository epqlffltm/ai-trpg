"""bookmarks

Revision ID: 86e3f940f02b
Revises: 53e2ee79e3fe
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '86e3f940f02b'
down_revision: str | Sequence[str] | None = '53e2ee79e3fe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 말의 책갈피(#982). 말 하나에 하나다. 말이나 세션의 행이 지워지면 함께 지워진다(app/bookmarks/models.py).
# 되돌리면 단 책갈피가 사라진다


def upgrade() -> None:
    op.create_table(
        'bookmarks',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('note', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_bookmarks_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_bookmarks_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_bookmarks')),
    )
    op.create_index(op.f('ix_bookmarks_conversation_id'), 'bookmarks', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bookmarks_conversation_id'), table_name='bookmarks')
    op.drop_table('bookmarks')
