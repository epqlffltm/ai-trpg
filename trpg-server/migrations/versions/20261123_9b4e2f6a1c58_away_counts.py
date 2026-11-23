"""away counts

Revision ID: 9b4e2f6a1c58
Revises: 5d2a8c1e7f30
Create Date: 2026-11-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '9b4e2f6a1c58'
down_revision: str | Sequence[str] | None = '5d2a8c1e7f30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 자리 비움(#1345).
#   - game_tables.away_counts: 앉은 사람마다 연속으로 선언을 내지 않은 라운드의 수. 빈 객체로 시작한다
#   - table_departures.kind 에 away(연속으로 내지 않아 서버가 뺐다)를 더한다
# 되돌리면 칸을 지우고, away 로 떠난 줄은 dropped(서버가 뺐다)로 바꿔 옛 조건에 맞춘다


def upgrade() -> None:
    op.add_column(
        'game_tables',
        sa.Column('away_counts', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_game_tables_away_counts_is_object'), 'game_tables', "jsonb_typeof(away_counts) = 'object'"
    )
    op.drop_constraint(op.f('ck_table_departures_kind_allowed'), 'table_departures', type_='check')
    op.create_check_constraint(
        op.f('ck_table_departures_kind_allowed'), 'table_departures', "kind IN ('left', 'kicked', 'dropped', 'away')"
    )


def downgrade() -> None:
    op.execute("UPDATE table_departures SET kind = 'dropped' WHERE kind = 'away'")
    op.drop_constraint(op.f('ck_table_departures_kind_allowed'), 'table_departures', type_='check')
    op.create_check_constraint(
        op.f('ck_table_departures_kind_allowed'), 'table_departures', "kind IN ('left', 'kicked', 'dropped')"
    )
    op.drop_constraint(op.f('ck_game_tables_away_counts_is_object'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'away_counts')
