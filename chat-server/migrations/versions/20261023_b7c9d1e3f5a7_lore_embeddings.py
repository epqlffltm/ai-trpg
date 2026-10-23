"""lore embeddings

Revision ID: b7c9d1e3f5a7
Revises: a6b8c0d2e4f6
Create Date: 2026-10-23 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = 'b7c9d1e3f5a7'
down_revision: str | Sequence[str] | None = 'a6b8c0d2e4f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 로어북 항목의 벡터(#672, app/lore/models.py). vector 타입은 extensions 스키마의 pgvector 다.
# chat 계정이 그 스키마를 쓸 수 있어야 한다(docker/postgres/init/09-chat-role.sql 의 GRANT USAGE)


def upgrade() -> None:
    op.create_table(
        'lore_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.String(length=40), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_lore_embeddings_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_embeddings')),
        sa.UniqueConstraint(
            'character_id', 'model', 'lorebook_id', 'entry_id', name=op.f('uq_lore_embeddings_character_id')
        ),
    )


def downgrade() -> None:
    op.drop_table('lore_embeddings')
