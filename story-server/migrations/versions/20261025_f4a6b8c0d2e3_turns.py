"""turns

Revision ID: f4a6b8c0d2e3
Revises: e3f5a7b9c1d2
Create Date: 2026-10-25 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f4a6b8c0d2e3'
down_revision: str | Sequence[str] | None = 'e3f5a7b9c1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 말 한 번의 표들(app/conversations/models.py 의 messages, message_states, app/turns/models.py 의 generations)과
# 세션의 지금 가지의 끝(active_leaf_id), 답을 쓰는 중인 시각(generating_since). chat 서버의 표와 같은 모양이다.
# 다른 것: 답이 말 조각(segments)과 그때의 장면의 인물(cast)을 갖고, 상태는 말에 붙은 표(message_states)에 있다.
# 세션과 말이 서로 가리킨다. 그래서 세션의 그 외래 키는 말의 표를 만든 뒤에 따로 건다. 지울 때는 그것부터 뗀다


def upgrade() -> None:
    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('segments', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('cast', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'action')", name=op.f('ck_messages_role_allowed')),
        sa.CheckConstraint("status IN ('complete', 'partial')", name=op.f('ck_messages_status_allowed')),
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
    op.create_table(
        'generations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=False),
        sa.Column('price_code', sa.String(length=120), nullable=False),
        sa.Column('billing_status', sa.String(length=20), nullable=False),
        sa.Column('settle_attempts', sa.Integer(), nullable=False),
        sa.Column('next_settle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.Column('error_code', sa.String(length=60), nullable=True),
        sa.Column('dropped_segments', sa.Integer(), server_default='0', nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_status IN ('pending', 'held', 'declined', 'capture_due', 'release_due', 'captured', "
            "'released', 'failed')",
            name=op.f('ck_generations_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('complete', 'partial', 'failed')",
            name=op.f('ck_generations_outcome_allowed'),
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_generations_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_generations_message_id_messages'), ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'], ['ai_models.slug'], name=op.f('fk_generations_model_slug_ai_models'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['messages.id'], name=op.f('fk_generations_parent_id_messages'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_generations')),
        sa.UniqueConstraint('reference', name=op.f('uq_generations_reference')),
    )
    op.create_index(
        'ix_generations_billing_status_next_settle_at',
        'generations',
        ['billing_status', 'next_settle_at'],
        unique=False,
    )
    op.create_index(op.f('ix_generations_conversation_id'), 'generations', ['conversation_id'], unique=False)
    op.create_table(
        'message_states',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_message_states_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_message_states')),
    )
    op.add_column('conversations', sa.Column('active_leaf_id', sa.Uuid(), nullable=True))
    op.add_column('conversations', sa.Column('generating_since', sa.DateTime(timezone=True), nullable=True))
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
    op.drop_column('conversations', 'generating_since')
    op.drop_column('conversations', 'active_leaf_id')
    op.drop_table('message_states')
    op.drop_index(op.f('ix_generations_conversation_id'), table_name='generations')
    op.drop_index('ix_generations_billing_status_next_settle_at', table_name='generations')
    op.drop_table('generations')
    op.drop_index('ix_messages_conversation_parent', table_name='messages')
    op.drop_table('messages')
