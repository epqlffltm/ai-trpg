"""conversations

Revision ID: d2e4f6a8b0c1
Revises:
Create Date: 2026-10-24 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd2e4f6a8b0c1'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# story 서버의 첫 테이블들(app/conversations/models.py). 가져온 세계관의 판의 사본과 세션


def upgrade() -> None:
    op.create_table(
        'worlds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_worlds_rating_allowed')),
        sa.CheckConstraint('version >= 1', name=op.f('ck_worlds_version_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_worlds')),
        sa.UniqueConstraint('owner_id', 'source_id', 'version', name='uq_worlds_owner_source_version'),
    )
    op.create_table(
        'conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_conversations_world_id_worlds'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    )
    op.create_index('ix_conversations_owner_updated', 'conversations', ['owner_id', 'updated_at'], unique=False)
    op.create_index(op.f('ix_conversations_world_id'), 'conversations', ['world_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversations_world_id'), table_name='conversations')
    op.drop_index('ix_conversations_owner_updated', table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('worlds')
