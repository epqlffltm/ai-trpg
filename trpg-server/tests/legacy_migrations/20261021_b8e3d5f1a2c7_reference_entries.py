"""reference entries

Revision ID: b8e3d5f1a2c7
Revises: f2c7a9d4b1e8
Create Date: 2026-10-21 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'b8e3d5f1a2c7'
down_revision: str | Sequence[str] | None = 'f2c7a9d4b1e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료(#482)의 줄과 그 벡터(app/references/models.py). 줄은 관리 명령(scripts/references.py)이 넣는다.
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
SOURCES = "source IN ('srd51')"
KINDS = "kind IN ('monster', 'item')"


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
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cardinality(aliases) <= 5', name=op.f('ck_reference_entries_aliases_count')),
        sa.CheckConstraint('char_length(content) <= 1000', name=op.f('ck_reference_entries_content_length')),
        sa.CheckConstraint(KINDS, name=op.f('ck_reference_entries_kind_allowed')),
        sa.CheckConstraint(SOURCES, name=op.f('ck_reference_entries_source_allowed')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_entries')),
        sa.UniqueConstraint('source', 'key', name=op.f('uq_reference_entries_source')),
    )
    # pgvector 는 로어북의 벡터(c5e7a9b1d3f5)가 이미 켜져 있는지 보았다
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


def downgrade() -> None:
    op.drop_table('reference_embeddings')
    op.drop_table('reference_entries')
