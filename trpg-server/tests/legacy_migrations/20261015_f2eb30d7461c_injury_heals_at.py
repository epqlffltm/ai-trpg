"""injury heals at

Revision ID: f2eb30d7461c
Revises: ed3db516b4b6
Create Date: 2026-10-15 15:10:28.465700

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2eb30d7461c'
down_revision: str | Sequence[str] | None = 'ed3db516b4b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 아직 낫지 않은 오래 가는 부상(테이블의 판에 굳은 규칙에서 healing 이 heals 인 것)을 시각으로 옮긴다.
# 그 부상은 ends_after_round 라운드가 닫힐 때 나을 것이었다. 지금 열린 라운드(R)가 닫힐 때 장면은
# 시계 + 걸음에서 끝나고, 라운드마다 판의 기본 걸음(rm)이 흐른다고 보면 그 라운드가 닫힐 때의 장면 끝은
# 시계 + (ends_after_round - R + 1) * rm 이다. 그 시각을 나을 시각으로 적는다. 같은 라운드가 닫힐 때 낫는다.
# 판에 시계가 없으면(형식 24 앞) 라운드 하나에 10분이다(DEFAULT_ROUND_MINUTES).
# 판에 부상 규칙이 없는 옛 형식의 테이블은 옮기지 않는다.
# 그 부상은 라운드로 낫는다(규칙을 읽어 오래 가는 것이면 나은 것으로 본다)
TO_MINUTES = """
UPDATE table_injuries AS ti
SET heals_at = c.minutes
             + (ti.ends_after_round - r.number + 1)
             * COALESCE((t.content -> 'clock' ->> 'round_minutes')::int, 10),
    ends_after_round = NULL
FROM game_tables AS t
JOIN table_clocks AS c ON c.table_id = t.id
JOIN LATERAL (SELECT max(number) AS number FROM table_rounds WHERE table_id = t.id) AS r ON true
WHERE ti.table_id = t.id
  AND ti.ended_at IS NULL
  AND ti.ends_after_round IS NOT NULL
  AND r.number IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(t.content -> 'rulebook' -> 'rules' -> 'injuries') AS rule
      WHERE rule ->> 'key' = ti.injury AND rule ->> 'healing' = 'heals'
  )
"""

# 되돌릴 때는 남은 시간을 라운드로 바꾼다. 생긴 라운드보다 뒤여야 한다(ends_after_start)
TO_ROUNDS = """
UPDATE table_injuries AS ti
SET ends_after_round = GREATEST(
        ti.round_number + 1,
        r.number - 1 + CEIL(
            (ti.heals_at - c.minutes)::numeric / COALESCE((t.content -> 'clock' ->> 'round_minutes')::int, 10)
        )::int
    ),
    heals_at = NULL
FROM game_tables AS t
JOIN table_clocks AS c ON c.table_id = t.id
JOIN LATERAL (SELECT max(number) AS number FROM table_rounds WHERE table_id = t.id) AS r ON true
WHERE ti.table_id = t.id AND ti.heals_at IS NOT NULL
"""


def upgrade() -> None:
    op.add_column('table_injuries', sa.Column('heals_at', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_injuries_one_end'), 'table_injuries', 'ends_after_round IS NULL OR heals_at IS NULL'
    )
    op.create_check_constraint(
        op.f('ck_table_injuries_heals_at_not_negative'), 'table_injuries', 'heals_at IS NULL OR heals_at >= 0'
    )
    op.execute(TO_MINUTES)


def downgrade() -> None:
    op.execute(TO_ROUNDS)
    op.drop_constraint(op.f('ck_table_injuries_heals_at_not_negative'), 'table_injuries', type_='check')
    op.drop_constraint(op.f('ck_table_injuries_one_end'), 'table_injuries', type_='check')
    op.drop_column('table_injuries', 'heals_at')
