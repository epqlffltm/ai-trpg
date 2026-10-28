"""lore embeddings

Revision ID: f0a2b4c6d8e0
Revises: e9f1a3b5c7d9
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = 'f0a2b4c6d8e0'
down_revision: str | Sequence[str] | None = 'e9f1a3b5c7d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세계관의 로어북 항목의 벡터(app/lore/models.py, chat 의 표와 같은 모양).
# vector 타입은 extensions 스키마의 pgvector 다.
# story 계정이 그 스키마를 쓸 수 있어야 한다(docker/postgres/init/10-story-role.sql 의 GRANT USAGE)


def upgrade() -> None:
    op.create_table(
        'lore_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.String(length=40), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_lore_embeddings_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_embeddings')),
        sa.UniqueConstraint('world_id', 'model', 'lorebook_id', 'entry_id', name=op.f('uq_lore_embeddings_world_id')),
    )


def downgrade() -> None:
    op.drop_table('lore_embeddings')
