"""references

Revision ID: 2234ca7672b7
Revises: 8a627803a47c
Create Date: 2026-11-23 10:04:11.722938

참고 자료(SRD 5.1, 위키백과)의 표 둘과 세션의 켜기(#1338).
표의 모양은 trpg, chat 의 것과 같다(reference_core/columns.py).
표는 비어서 생긴다. 줄은 운영자가 관리 명령으로 넣는다(scripts/references.py load → index).
있던 세션은 모두 꺼진 채다. 사람이 켤 때까지 카드에 섞지 않는다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = '2234ca7672b7'
down_revision: str | Sequence[str] | None = '8a627803a47c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reference_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('aliases', postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('name_ko', sa.String(length=100), server_default='', nullable=False),
        sa.Column('content_ko', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('monster', 'item', 'topic')", name=op.f('ck_reference_entries_kind_allowed')),
        sa.CheckConstraint("source IN ('srd51', 'wikipedia')", name=op.f('ck_reference_entries_source_allowed')),
        sa.CheckConstraint('cardinality(aliases) <= 5', name=op.f('ck_reference_entries_aliases_count')),
        sa.CheckConstraint('char_length(content) <= 1000', name=op.f('ck_reference_entries_content_length')),
        sa.CheckConstraint('char_length(content_ko) <= 1000', name=op.f('ck_reference_entries_content_ko_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_entries')),
        sa.UniqueConstraint('source', 'key', name=op.f('uq_reference_entries_source')),
    )
    op.create_table(
        'reference_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reference_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['reference_id'],
            ['reference_entries.id'],
            name=op.f('fk_reference_embeddings_reference_id_reference_entries'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_embeddings')),
        sa.UniqueConstraint('model', 'reference_id', name=op.f('uq_reference_embeddings_model')),
    )
    op.create_index(
        op.f('ix_reference_embeddings_reference_id'), 'reference_embeddings', ['reference_id'], unique=False
    )
    op.add_column(
        'conversations', sa.Column('references_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('conversations', 'references_enabled')
    op.drop_index(op.f('ix_reference_embeddings_reference_id'), table_name='reference_embeddings')
    op.drop_table('reference_embeddings')
    op.drop_table('reference_entries')
