"""treatment

Revision ID: e0b2c4d6f8a1
Revises: c4e6a8b0d2f4
Create Date: 2026-10-11 23:30:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e0b2c4d6f8a1'
down_revision: str | Sequence[str] | None = 'c4e6a8b0d2f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 치료. 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다.
# 앱의 코드를 가져오지 않고 여기에 적어 둔다
TREATMENT = {
    'ability': 'wis',
    'mishaps': {
        'sides': 100,
        'rows': [
            {'low': 1, 'high': 1, 'kind': 'fatal', 'rounds': None, 'magnitude': None},
            {'low': 2, 'high': 10, 'kind': 'worsen', 'rounds': 10, 'magnitude': 'moderate'},
            {'low': 11, 'high': 30, 'kind': 'worsen', 'rounds': 5, 'magnitude': None},
            {'low': 31, 'high': 50, 'kind': 'pain', 'rounds': None, 'magnitude': 'light'},
            {'low': 51, 'high': 100, 'kind': 'nothing', 'rounds': None, 'magnitude': None},
        ],
    },
}

# 부상마다 채우는 치료의 칸. 여기 없는 부상은 치료할 수 없다(두 칸 모두 비운다)
TREATABLE = {
    'broken_arm': {'treat_difficulty': 'hard', 'treat_rounds': 10},
    'leg_wound': {'treat_difficulty': 'medium', 'treat_rounds': 10},
}
UNTREATABLE = {'treat_difficulty': None, 'treat_rounds': None}

# 부상이 없던 판(형식 13 이하)으로 만든 테이블의 오래 가는 부상. 그 판은 읽을 때 SRD5 의 부상으로 올려 읽는다
FALLBACK_LASTING = [
    {'key': 'broken_arm', 'healing': 'heals', 'rounds': 30},
    {'key': 'leg_wound', 'healing': 'heals', 'rounds': 20},
]

# 테이블마다 오래 가는 부상의 이름과 낫기까지의 라운드 수. 테이블의 판의 복사본에서 읽는다
LASTING = """
    SELECT t.id AS table_id, item->>'key' AS key, CAST(item->>'rounds' AS INTEGER) AS rounds
    FROM game_tables AS t,
         jsonb_array_elements(COALESCE(t.content->'rulebook'->'rules'->'injuries', CAST(:fallback AS JSONB))) AS item
    WHERE item->>'healing' = 'heals'
"""

# 룰북의 rules 문서에 치료를 더한다. 이미 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다
FILL_TREATMENT = (
    "UPDATE rulebooks SET rules = rules || jsonb_build_object('treatment', CAST(:value AS JSONB)) "
    "WHERE NOT jsonb_exists(rules, 'treatment')"
)

# 부상마다 치료의 칸을 더한다. 이미 칸이 있는 부상은 건드리지 않는다. 순서는 그대로다
FILL_INJURIES = (
    "UPDATE rulebooks SET rules = jsonb_set(rules, '{injuries}', ("
    '  SELECT COALESCE(jsonb_agg('
    "    CASE WHEN jsonb_exists(item, 'treat_difficulty') THEN item"
    "         ELSE item || COALESCE(CAST(:treatable AS JSONB) -> (item->>'key'), CAST(:untreatable AS JSONB))"
    '    END ORDER BY position), CAST(:empty AS JSONB))'
    "  FROM jsonb_array_elements(rules->'injuries') WITH ORDINALITY AS entry(item, position)"
    ")) WHERE jsonb_exists(rules, 'injuries')"
)

# 이미 입고 있는 오래 가는 부상에 나을 라운드를 적는다. 전에는 비어 있었다(짧은 것에만 적었다).
# 생긴 라운드에 그 테이블의 규칙의 라운드 수를 더한다
FILL_HEAL_ROUNDS = (
    'UPDATE table_injuries AS ti SET ends_after_round = ti.round_number + lasting.rounds '
    f'FROM ({LASTING}) AS lasting '
    'WHERE ti.table_id = lasting.table_id AND ti.injury = lasting.key '
    'AND ti.ends_after_round IS NULL AND ti.ended_at IS NULL'
)

# 내릴 때. 오래 가는 부상의 나을 라운드를 다시 비운다. 전의 코드는 오래 가는 부상에 나을 라운드가 없다고 본다
CLEAR_HEAL_ROUNDS = (
    'UPDATE table_injuries AS ti SET ends_after_round = NULL '
    f'FROM ({LASTING}) AS lasting '
    'WHERE ti.table_id = lasting.table_id AND ti.injury = lasting.key AND ti.ended_at IS NULL'
)

DROP_INJURY_FIELDS = (
    "UPDATE rulebooks SET rules = jsonb_set(rules, '{injuries}', ("
    "  SELECT COALESCE(jsonb_agg(item - 'treat_difficulty' - 'treat_rounds' ORDER BY position), CAST(:empty AS JSONB))"
    "  FROM jsonb_array_elements(rules->'injuries') WITH ORDINALITY AS entry(item, position)"
    ")) WHERE jsonb_exists(rules, 'injuries')"
)


def fill_treatment() -> sa.TextClause:
    return sa.text(FILL_TREATMENT).bindparams(value=json.dumps(TREATMENT))


def fill_injuries() -> sa.TextClause:
    return sa.text(FILL_INJURIES).bindparams(
        treatable=json.dumps(TREATABLE), untreatable=json.dumps(UNTREATABLE), empty=json.dumps([])
    )


def fill_heal_rounds() -> sa.TextClause:
    return sa.text(FILL_HEAL_ROUNDS).bindparams(fallback=json.dumps(FALLBACK_LASTING))


def upgrade() -> None:
    op.execute(fill_treatment())
    op.execute(fill_injuries())
    op.execute(fill_heal_rounds())


def downgrade() -> None:
    op.execute(sa.text(CLEAR_HEAL_ROUNDS).bindparams(fallback=json.dumps(FALLBACK_LASTING)))
    op.execute(sa.text(DROP_INJURY_FIELDS).bindparams(empty=json.dumps([])))
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'treatment'"))
