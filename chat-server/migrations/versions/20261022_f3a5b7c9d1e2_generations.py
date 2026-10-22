"""generations

Revision ID: f3a5b7c9d1e2
Revises: e2f4a6c8b0d1
Create Date: 2026-10-22 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a5b7c9d1e2'
down_revision: str | Sequence[str] | None = 'e2f4a6c8b0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 말 한 번(app/turns/). 호출과 청구의 기록(generations)과,
# 한 대화에 한 생성을 지키는 차례(conversations.generating_since)


def upgrade() -> None:
    op.create_table(
        'generations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=False),
        sa.Column('price_code', sa.String(length=120), nullable=False),
        sa.Column('billing_status', sa.String(length=20), nullable=False),
        sa.Column('settle_attempts', sa.Integer(), nullable=False),
        sa.Column('next_settle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.Column('error_code', sa.String(length=60), nullable=True),
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
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_generations_message_id_messages'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'], ['ai_models.slug'], name=op.f('fk_generations_model_slug_ai_models'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['messages.id'], name=op.f('fk_generations_parent_id_messages'), ondelete='CASCADE'
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
    op.add_column('conversations', sa.Column('generating_since', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'generating_since')
    op.drop_index(op.f('ix_generations_conversation_id'), table_name='generations')
    op.drop_index('ix_generations_billing_status_next_settle_at', table_name='generations')
    op.drop_table('generations')
