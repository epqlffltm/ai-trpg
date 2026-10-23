"""lorebooks

Revision ID: c1e3a5b7d9f0
Revises: b0d2f4a6c8e9
Create Date: 2026-10-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c1e3a5b7d9f0'
down_revision: str | Sequence[str] | None = 'b0d2f4a6c8e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 로어북(#672). 초안과 판, 캐릭터가 가리키는 로어북의 id 들. 있던 캐릭터는 빈 목록이다


def upgrade() -> None:
    op.create_table(
        'lorebooks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('entries', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_lorebooks_published_paired')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lorebooks')),
    )
    op.create_index(op.f('ix_lorebooks_owner_id'), 'lorebooks', ['owner_id'], unique=False)
    op.create_table(
        'lorebook_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('number >= 1', name=op.f('ck_lorebook_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['lorebook_id'],
            ['lorebooks.id'],
            name=op.f('fk_lorebook_versions_lorebook_id_lorebooks'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lorebook_versions')),
        sa.UniqueConstraint('lorebook_id', 'number', name='uq_lorebook_versions_number'),
    )
    op.create_index(op.f('ix_lorebook_versions_lorebook_id'), 'lorebook_versions', ['lorebook_id'], unique=False)
    op.add_column(
        'characters', sa.Column('lorebooks', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('characters', 'lorebooks')
    op.drop_index(op.f('ix_lorebook_versions_lorebook_id'), table_name='lorebook_versions')
    op.drop_table('lorebook_versions')
    op.drop_index(op.f('ix_lorebooks_owner_id'), table_name='lorebooks')
    op.drop_table('lorebooks')
