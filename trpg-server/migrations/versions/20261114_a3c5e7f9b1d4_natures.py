"""natures

Revision ID: a3c5e7f9b1d4
Revises: f2b4d6e8a0c3
Create Date: 2026-11-14 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c5e7f9b1d4'
down_revision: str | Sequence[str] | None = 'f2b4d6e8a0c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북이 성질을 정한다(#886). 룰북의 규칙에 성질(natures)과 몬스터의 타입마다의 면역(monster_immunities)을 더한다.
# 이미 있는 룰북은 그때 엔진에 박혀 있던 값(다섯 성질, 언데드는 독, 구조물은 독과 정신)으로 채운다. 하던 대로 돈다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_66, 같은 값).
# 되돌리면 둘을 지우고, 시나리오의 몬스터 시트의 면역과 약함에서 다섯이 아닌 성질을 뺀다(그때는 다섯뿐이었다).
# 앱의 코드를 가져오지 않는다

CLASSIC_NATURES = [
    {'key': 'poison', 'name': '독', 'category': None},
    {'key': 'stun', 'name': '기절', 'category': None},
    {'key': 'sense', 'name': '감각', 'category': None},
    {'key': 'body', 'name': '몸', 'category': None},
    {'key': 'mind', 'name': '정신', 'category': None},
]
CLASSIC_MONSTER_IMMUNITIES = [
    {'kind': 'undead', 'natures': ['poison']},
    {'kind': 'construct', 'natures': ['poison', 'mind']},
]
CLASSIC_KEYS = {nature['key'] for nature in CLASSIC_NATURES}


def with_natures(rules: dict) -> dict:
    """룰북의 규칙. 성질과 타입마다의 면역이 없으면 그때의 값을 채운다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    filled = rules if 'natures' in rules else {**rules, 'natures': CLASSIC_NATURES}
    if 'monster_immunities' in filled:
        return filled
    return {**filled, 'monster_immunities': CLASSIC_MONSTER_IMMUNITIES}


def without_natures(rules: dict) -> dict:
    """되돌릴 때. 성질과 타입마다의 면역을 뺀다."""
    return {key: value for key, value in rules.items() if key not in ('natures', 'monster_immunities')}


def classic_only(sheet: dict) -> dict:
    """되돌릴 때. 몬스터 시트 하나의 면역과 약함에서 다섯이 아닌 성질을 뺀다."""
    fields = {key: [one for one in sheet.get(key) or [] if one in CLASSIC_KEYS] for key in ('immune', 'vulnerable')}
    return {**sheet, **{key: value for key, value in fields.items() if key in sheet}}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def rewrite_monster_sheets(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 몬스터 시트를 classic_only 로 고쳐 쓴다. 바뀐 것만 적는다."""
    for scenario_id, sheets in connection.execute(sa.text('SELECT asset_id, monster_sheets FROM scenarios')).all():
        changed = [classic_only(sheet) for sheet in sheets or []]
        if changed != (sheets or []):
            connection.execute(
                sa.text('UPDATE scenarios SET monster_sheets = CAST(:sheets AS JSONB) WHERE asset_id = :id'),
                {'sheets': json.dumps(changed), 'id': scenario_id},
            )


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_natures)


def downgrade() -> None:
    rewrite_monster_sheets(op.get_bind())
    rewrite_rulebooks(op.get_bind(), without_natures)
