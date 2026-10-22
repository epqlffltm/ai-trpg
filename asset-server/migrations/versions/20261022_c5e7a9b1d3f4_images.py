"""images

Revision ID: c5e7a9b1d3f4
Revises: b4d6f8a0c2e3
Create Date: 2026-10-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e7a9b1d3f4'
down_revision: str | Sequence[str] | None = 'b4d6f8a0c2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 그림의 행(#566, app/images/models.py). 바이트는 저장소(SeaweedFS, S3)에 그림의 id 로 있다


def upgrade() -> None:
    op.create_table(
        'images',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('format', sa.String(length=10), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("format IN ('png', 'jpeg', 'webp')", name=op.f('ck_images_format_allowed')),
        sa.CheckConstraint('byte_size > 0 AND width > 0 AND height > 0', name=op.f('ck_images_size_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_images')),
    )
    op.create_index(op.f('ix_images_owner_id'), 'images', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_images_owner_id'), table_name='images')
    op.drop_table('images')
