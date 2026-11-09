"""rulebook defense

Revision ID: bbf9dad39cec
Revises: d3a1e5c7b9f0
Create Date: 2026-12-12 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'bbf9dad39cec'
down_revision: str | Sequence[str] | None = 'd3a1e5c7b9f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 맞서는 굴림(#254). 룰북의 규칙에 막는 규칙(defense: 받는 쪽이 굴리는 능력치)을 더한다.
# 이미 있는 룰북은 그 템플릿의 것으로 채운다(srd5 는 민첩, light 는 재치, horror 는 날램).
# 모르는 템플릿이거나 그 능력치가 없으면 차례를 정하는 능력치, 그것도 없으면 첫 능력치다.
# 그 뒤에 게시하는 판부터 공격이 맞서는 굴림이다.
# 굳힌 판은 고치지 않는다. 읽을 때 막는 규칙이 없는 것으로 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_69).
# 되돌리면 룰북의 규칙에서 막는 규칙을 뺀다(그때의 모양은 모르는 칸을 받지 않는다). 앱의 코드를 가져오지 않는다

TEMPLATE_DEFENSES = {'srd5': 'dex', 'light': 'wits', 'horror': 'agility'}


def defense_ability(rules: dict) -> str:
    """채울 막는 능력치. 템플릿의 것, 없으면 차례를 정하는 능력치, 그것도 없으면 첫 능력치다."""
    keys = [ability['key'] for ability in rules['abilities']]
    for candidate in (TEMPLATE_DEFENSES.get(rules.get('template')), rules.get('initiative_ability')):
        if candidate in keys:
            return candidate
    return keys[0]


def with_defense(rules: dict) -> dict:
    """룰북의 규칙. 막는 규칙이 없으면 채운다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    return rules if 'defense' in rules else {**rules, 'defense': {'ability': defense_ability(rules)}}


def without_defense(rules: dict) -> dict:
    """되돌릴 때. 룰북의 규칙에서 막는 규칙을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'defense'}


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
    rewrite_rulebooks(op.get_bind(), with_defense)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_defense)
