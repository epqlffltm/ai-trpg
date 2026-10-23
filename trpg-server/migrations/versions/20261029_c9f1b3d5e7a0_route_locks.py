"""route locks

Revision ID: c9f1b3d5e7a0
Revises: df5333cd6beb
Create Date: 2026-10-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9f1b3d5e7a0'
down_revision: str | Sequence[str] | None = 'df5333cd6beb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 길의 자물쇠(#281). 테이블마다 판에 자물쇠를 적은 길이 지금 잠겨 있는지를 적는다.
# 길의 조건(넘기 판정, 자물쇠의 열쇠)은 판(content)의 문서에 있다. 시나리오의 칸은 routes 의 JSONB 그대로다


def upgrade() -> None:
    # 있던 테이블은 자물쇠가 있는 판으로 시작하지 않았다
    op.create_table(
        'table_route_locks',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('from_place', sa.Uuid(), nullable=False),
        sa.Column('to_place', sa.Uuid(), nullable=False),
        sa.Column('locked', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_table_route_locks_table_id_game_tables'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'from_place', 'to_place', name=op.f('pk_table_route_locks')),
    )


def downgrade() -> None:
    op.drop_table('table_route_locks')
