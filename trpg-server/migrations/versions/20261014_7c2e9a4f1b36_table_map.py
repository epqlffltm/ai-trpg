"""table map

Revision ID: 7c2e9a4f1b36
Revises: 5a1c7e3b9d20
Create Date: 2026-10-14 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7c2e9a4f1b36'
down_revision: str | Sequence[str] | None = '5a1c7e3b9d20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 테이블은 서 본 곳도 위치도 없다. 맵이 있는 판이어도 방장이 옮기기 전까지 캐릭터의 위치는 비어 있다
    op.create_table(
        'table_visits',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('visited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_visits_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_visits')),
    )
    op.add_column('table_sheets', sa.Column('place_id', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('table_sheets', 'place_id')
    op.drop_table('table_visits')
