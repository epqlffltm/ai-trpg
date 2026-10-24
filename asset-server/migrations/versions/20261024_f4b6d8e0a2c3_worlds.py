"""worlds

Revision ID: f4b6d8e0a2c3
Revises: e3a5c7e9f1b2
Create Date: 2026-10-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f4b6d8e0a2c3'
down_revision: str | Sequence[str] | None = 'e3a5c7e9f1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# story 의 세계관(#591). 초안, 판, 판에 쓰인 그림. 세계관의 목록 칸(시간대, 장소, 인물 …)은 문서(JSONB)다


def upgrade() -> None:
    op.create_table(
        'worlds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('intro_html', sa.Text(), server_default='', nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=20)), server_default='{}', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('slots', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_slot', sa.String(length=40), nullable=True),
        sa.Column('deadline_days', sa.Integer(), nullable=True),
        sa.Column('after_ending', sa.String(length=10), server_default='end', nullable=False),
        sa.Column('show', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('places', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('paths', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_place', sa.String(length=40), nullable=True),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('cast', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('lorebooks', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False),
        sa.Column('rating', sa.String(length=10), server_default='all', nullable=False),
        sa.Column('visibility', sa.String(length=10), server_default='private', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("after_ending IN ('end', 'epilogue')", name=op.f('ck_worlds_after_allowed')),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_worlds_rating_allowed')),
        sa.CheckConstraint("visibility IN ('private', 'public')", name=op.f('ck_worlds_visibility_allowed')),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_worlds_published_paired')
        ),
        sa.CheckConstraint('cardinality(tags) <= 10', name=op.f('ck_worlds_tags_count')),
        sa.CheckConstraint(
            'deadline_days IS NULL OR deadline_days BETWEEN 1 AND 365', name=op.f('ck_worlds_deadline_range')
        ),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_worlds_image_id_images'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_worlds')),
    )
    op.create_index(op.f('ix_worlds_image_id'), 'worlds', ['image_id'], unique=False)
    op.create_index(op.f('ix_worlds_owner_id'), 'worlds', ['owner_id'], unique=False)
    op.create_table(
        'world_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_world_versions_rating_allowed')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_world_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_world_versions_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_world_versions')),
        sa.UniqueConstraint('world_id', 'number', name='uq_world_versions_number'),
    )
    op.create_index(op.f('ix_world_versions_world_id'), 'world_versions', ['world_id'], unique=False)
    op.create_table(
        'world_image_uses',
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_world_image_uses_image_id_images'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['world_versions.id'],
            name=op.f('fk_world_image_uses_version_id_world_versions'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('version_id', 'image_id', name=op.f('pk_world_image_uses')),
    )
    op.create_index(op.f('ix_world_image_uses_image_id'), 'world_image_uses', ['image_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_world_image_uses_image_id'), table_name='world_image_uses')
    op.drop_table('world_image_uses')
    op.drop_index(op.f('ix_world_versions_world_id'), table_name='world_versions')
    op.drop_table('world_versions')
    op.drop_index(op.f('ix_worlds_owner_id'), table_name='worlds')
    op.drop_index(op.f('ix_worlds_image_id'), table_name='worlds')
    op.drop_table('worlds')
