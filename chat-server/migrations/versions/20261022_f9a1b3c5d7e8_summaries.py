"""summaries

Revision ID: f9a1b3c5d7e8
Revises: e8f0a2b4c6d7
Create Date: 2026-10-22 23:59:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f9a1b3c5d7e8'
down_revision: str | Sequence[str] | None = 'e8f0a2b4c6d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 굴리는 요약(app/memory/summarizer.py). 첫 말부터 그 말까지의 요약이 그 말에 붙는다


def upgrade() -> None:
    op.create_table(
        'summaries',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_summaries_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_summaries_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_summaries')),
    )
    op.create_index(op.f('ix_summaries_conversation_id'), 'summaries', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_summaries_conversation_id'), table_name='summaries')
    op.drop_table('summaries')
