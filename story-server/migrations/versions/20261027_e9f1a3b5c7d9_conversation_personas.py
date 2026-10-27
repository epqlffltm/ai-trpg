"""conversation personas

Revision ID: e9f1a3b5c7d9
Revises: d8e0f2a4b6c8
Create Date: 2026-10-27 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e9f1a3b5c7d9'
down_revision: str | Sequence[str] | None = 'd8e0f2a4b6c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세션에 가져온 계정 페르소나의 사본(app/conversations/models.py 의 ConversationPersona). chat 의 표와 같은 모양이다.
# 지금까지의 세션은 페르소나 없이 시작한 것이라 행이 없다


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table('conversation_personas')
