"""resource thresholds

Revision ID: c9e1a3b5d7f0
Revises: b8d0f2a4c6e9
Create Date: 2026-11-10 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9e1a3b5d7f0'
down_revision: str | Sequence[str] | None = 'b8d0f2a4c6e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 수치의 문턱과 라운드마다의 변화(#804). 수치에 each_round, at_min, at_max 를 더한다. 비우면 없는 것이라
# 이미 있는 룰북과 굳힌 판은 그대로 읽힌다(고치지 않는다).
# 부상이 수치의 문턱으로도 생긴다(source 'resource').
# 되돌리면 문턱으로 생긴 부상을 지우고, 룰북의 수치에서 세 칸을 뺀다. 앱의 코드를 가져오지 않는다

SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource')"
OLD_SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item')"
NEW_FIELDS = ('each_round', 'at_min', 'at_max')


def without_thresholds(rules: dict) -> dict:
    """되돌릴 때. 수치마다 라운드마다의 변화와 문턱을 뺀다. 수치가 없는 규칙은 그대로다."""
    if not rules.get('resources'):
        return rules
    resources = [
        {key: value for key, value in resource.items() if key not in NEW_FIELDS} for resource in rules['resources']
    ]
    return {**rules, 'resources': resources}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def upgrade() -> None:
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', SOURCES)


def downgrade() -> None:
    # 문턱으로 생긴 부상은 되돌린 모양에 들어갈 자리가 없다. 지운다
    op.execute("DELETE FROM table_injuries WHERE source = 'resource'")
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', OLD_SOURCES)
    rewrite_rulebooks(op.get_bind(), without_thresholds)
