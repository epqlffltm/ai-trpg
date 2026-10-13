"""table items

Revision ID: 8a0d7f7760cc
Revises: ebdbe8b61196
Create Date: 2026-10-13 11:24:57.292685

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8a0d7f7760cc'
down_revision: str | Sequence[str] | None = 'ebdbe8b61196'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 캐릭터의 소지품(#202). 시트마다 물건 한 가지가 한 줄이다
    op.create_table(
        'table_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('count BETWEEN 1 AND 99', name=op.f('ck_table_items_count_range')),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_items_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_items_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_items')),
        sa.UniqueConstraint('sheet_id', 'entry_id', name='uq_table_items_entry'),
    )
    op.create_index(op.f('ix_table_items_table_id'), 'table_items', ['table_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_table_items_table_id'), table_name='table_items')
    op.drop_table('table_items')
