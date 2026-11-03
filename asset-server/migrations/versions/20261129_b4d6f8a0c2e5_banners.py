"""banners

Revision ID: b4d6f8a0c2e5
Revises: 3697d9b8eb2a
Create Date: 2026-11-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b4d6f8a0c2e5'
down_revision: str | Sequence[str] | None = '3697d9b8eb2a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'banners',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=True),
        sa.Column('world_id', sa.Uuid(), nullable=True),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name=op.f('ck_banners_period_order')),
        sa.CheckConstraint('num_nonnulls(character_id, world_id) = 1', name=op.f('ck_banners_one_target')),
        sa.CheckConstraint('position >= 0 AND position <= 999', name=op.f('ck_banners_position_range')),
        sa.ForeignKeyConstraint(
            ['character_id'], ['characters.id'], name=op.f('fk_banners_character_id_characters'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_banners_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_banners')),
    )
    op.create_index(op.f('ix_banners_character_id'), 'banners', ['character_id'], unique=False)
    op.create_index(op.f('ix_banners_world_id'), 'banners', ['world_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_banners_world_id'), table_name='banners')
    op.drop_index(op.f('ix_banners_character_id'), table_name='banners')
    op.drop_table('banners')
