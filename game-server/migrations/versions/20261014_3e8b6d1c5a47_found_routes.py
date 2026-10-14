"""found routes

Revision ID: 3e8b6d1c5a47
Revises: 7c2e9a4f1b36
Create Date: 2026-10-14 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3e8b6d1c5a47'
down_revision: str | Sequence[str] | None = '7c2e9a4f1b36'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 테이블은 찾은 숨긴 길이 없다
    op.create_table(
        'table_found_routes',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('from_place', sa.Uuid(), nullable=False),
        sa.Column('to_place', sa.Uuid(), nullable=False),
        sa.Column('found_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_table_found_routes_table_id_game_tables'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'from_place', 'to_place', name=op.f('pk_table_found_routes')),
    )


def downgrade() -> None:
    op.drop_table('table_found_routes')
