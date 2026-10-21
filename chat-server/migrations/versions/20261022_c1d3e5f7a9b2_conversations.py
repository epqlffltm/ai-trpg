"""conversations

Revision ID: c1d3e5f7a9b2
Revises:
Create Date: 2026-10-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c1d3e5f7a9b2'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# chat 서버의 첫 테이블들(app/conversations/models.py). 가져온 캐릭터의 판, 대화, 페르소나의 사본, 말.
# 대화와 말이 서로 가리킨다(대화의 active_leaf_id, 말의 conversation_id). 그래서 대화의 그 외래 키는
# 말의 표를 만든 뒤에 따로 건다. 지울 때는 그것부터 뗀다


def upgrade() -> None:
    op.create_table(
        'characters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_characters_rating_allowed')),
        sa.CheckConstraint('version >= 1', name=op.f('ck_characters_version_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_characters')),
        sa.UniqueConstraint('owner_id', 'source_id', 'version', name='uq_characters_owner_source_version'),
    )
    op.create_table(
        'conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('start_title', sa.Text(), nullable=False),
        sa.Column('start_situation', sa.Text(), nullable=False),
        sa.Column('active_leaf_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_conversations_character_id_characters'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    )
    op.create_index(op.f('ix_conversations_character_id'), 'conversations', ['character_id'], unique=False)
    op.create_index('ix_conversations_owner_updated', 'conversations', ['owner_id', 'updated_at'], unique=False)
    op.create_table(
        'conversation_personas',
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('age', sa.Text(), nullable=False),
        sa.Column('gender', sa.Text(), nullable=False),
        sa.Column('form_of_address', sa.Text(), nullable=False),
        sa.Column('speech_examples', sa.Text(), nullable=False),
        sa.Column('personality', sa.Text(), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_conversation_personas_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('conversation_id', name=op.f('pk_conversation_personas')),
    )
    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f('ck_messages_role_allowed')),
        sa.CheckConstraint("status IN ('complete', 'partial', 'failed')", name=op.f('ck_messages_status_allowed')),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_messages_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['messages.id'], name=op.f('fk_messages_parent_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    )
    op.create_index('ix_messages_conversation_parent', 'messages', ['conversation_id', 'parent_id'], unique=False)
    op.create_foreign_key(
        'fk_conversations_active_leaf_id_messages',
        'conversations',
        'messages',
        ['active_leaf_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_conversations_active_leaf_id_messages', 'conversations', type_='foreignkey')
    op.drop_index('ix_messages_conversation_parent', table_name='messages')
    op.drop_table('messages')
    op.drop_table('conversation_personas')
    op.drop_index('ix_conversations_owner_updated', table_name='conversations')
    op.drop_index(op.f('ix_conversations_character_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('characters')
