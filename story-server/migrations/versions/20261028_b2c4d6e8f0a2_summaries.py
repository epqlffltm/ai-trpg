"""summaries

Revision ID: b2c4d6e8f0a2
Revises: a1b3c5d7e9f1
Create Date: 2026-10-28 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c4d6e8f0a2'
down_revision: str | Sequence[str] | None = 'a1b3c5d7e9f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 굴리는 요약(app/memory/models.py 의 Summary, chat 의 표와 같은 모양). 요약한 마지막 말에 붙는다.
# 말이나 세션이 지워지면 함께 지워진다


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
