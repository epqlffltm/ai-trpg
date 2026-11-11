"""turn slots

Revision ID: d1f7b3a5c9e8
Revises: c9e5a1d3f7b4
Create Date: 2026-12-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd1f7b3a5c9e8'
down_revision: str | Sequence[str] | None = 'c9e5a1d3f7b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 차례대로 진행하는 테이블(#287)의 몬스터의 자리와 다음 차례까지 드는 태세.
#   - turn_foes: 이번 바퀴에 차례를 받은 몬스터와 싸우는 인물. 있던 테이블은 빈 목록이다
#   - turn_stances: 앉은 사람마다 다음 차례까지 드는 엄폐와 방어 태세. 있던 테이블은 빈 문서다
# 되돌리면 칸을 지운다. 그때 들던 태세는 사라진다


def upgrade() -> None:
    op.add_column(
        'game_tables',
        sa.Column(
            'turn_foes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        'game_tables',
        sa.Column(
            'turn_stances',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f('ck_game_tables_turn_foes_is_array'), 'game_tables', "jsonb_typeof(turn_foes) = 'array'"
    )
    op.create_check_constraint(
        op.f('ck_game_tables_turn_stances_is_object'), 'game_tables', "jsonb_typeof(turn_stances) = 'object'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_game_tables_turn_stances_is_object'), 'game_tables', type_='check')
    op.drop_constraint(op.f('ck_game_tables_turn_foes_is_array'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'turn_stances')
    op.drop_column('game_tables', 'turn_foes')
