"""characters

Revision ID: b4d6f8a0c2e3
Revises: a3c5e7f9b1d2
Create Date: 2026-10-21 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b4d6f8a0c2e3'
down_revision: str | Sequence[str] | None = 'a3c5e7f9b1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 초안과 판(#567, app/characters/models.py). 판은 바뀌지 않는 문서이고 캐릭터를 지우면 함께 지워진다


def upgrade() -> None:
    op.create_table(
        'characters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('intro_html', sa.Text(), server_default='', nullable=False),
        sa.Column('greeting', sa.Text(), server_default='', nullable=False),
        sa.Column('speech_examples', sa.Text(), server_default='', nullable=False),
        sa.Column('age', sa.String(length=20), server_default='', nullable=False),
        sa.Column('gender', sa.String(length=20), server_default='', nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=20)), server_default='{}', nullable=False),
        sa.Column('starts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('rating', sa.String(length=10), server_default='all', nullable=False),
        sa.Column('visibility', sa.String(length=10), server_default='private', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_characters_rating_allowed')),
        sa.CheckConstraint("visibility IN ('private', 'public')", name=op.f('ck_characters_visibility_allowed')),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_characters_published_paired')
        ),
        sa.CheckConstraint('cardinality(tags) <= 10', name=op.f('ck_characters_tags_count')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_characters')),
    )
    op.create_index(op.f('ix_characters_owner_id'), 'characters', ['owner_id'], unique=False)
    op.create_table(
        'character_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_character_versions_rating_allowed')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_character_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_versions_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_character_versions')),
        sa.UniqueConstraint('character_id', 'number', name='uq_character_versions_number'),
    )
    op.create_index(op.f('ix_character_versions_character_id'), 'character_versions', ['character_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_character_versions_character_id'), table_name='character_versions')
    op.drop_table('character_versions')
    op.drop_index(op.f('ix_characters_owner_id'), table_name='characters')
    op.drop_table('characters')
