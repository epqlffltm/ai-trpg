"""npc places

Revision ID: b8e0a2c4d6f9
Revises: a7d9f1b3c5e8
Create Date: 2026-10-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8e0a2c4d6f9'
down_revision: str | Sequence[str] | None = 'a7d9f1b3c5e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 인물의 자리(#282). 시나리오에 인물마다 처음 있는 장소를 적는 칸, 테이블의 인물이 지금 있는 장소,
# 판의 사건이 옮긴 인물들을 적는 칸이다


def upgrade() -> None:
    # 있던 시나리오는 자리를 적은 인물이 없다. 모두 지금처럼 장면의 글로 나온다
    op.add_column(
        'scenarios',
        sa.Column(
            'npc_places',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_npc_places_count'), 'scenarios', 'jsonb_array_length(npc_places) <= 100'
    )
    # 있던 테이블의 인물은 자리가 없다
    op.add_column('table_npcs', sa.Column('place_id', sa.Uuid(), nullable=True))
    # 있던 사건은 인물을 옮기지 않았다
    op.add_column(
        'table_happenings',
        sa.Column(
            'npc_moves',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('table_happenings', 'npc_moves')
    op.drop_column('table_npcs', 'place_id')
    op.drop_constraint(op.f('ck_scenarios_npc_places_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'npc_places')
