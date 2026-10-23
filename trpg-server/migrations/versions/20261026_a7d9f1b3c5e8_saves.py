"""saves

Revision ID: a7d9f1b3c5e8
Revises: f6c8e0a2b4d7
Create Date: 2026-10-26 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d9f1b3c5e8'
down_revision: str | Sequence[str] | None = 'f6c8e0a2b4d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세이브와 관통(#276). 룰북의 방어 방식에 세이브의 목표값(save_target)과 관통의 기준값(pierce_base)을 더한다.
# 방어 방식이 있는 룰북은 세이브의 목표값이 없고(ac 나 reduce 다) 관통의 기준값이 10 이다.
# 방어 방식이 없으면 그대로 없다.
# 판은 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_48). 앱의 코드를 가져오지 않는다

PIERCE_BASE = 10


def with_pierce(rules: dict) -> dict:
    """방어 방식에 세이브의 목표값과 관통의 기준값을 채운다. 이미 있거나 방어 방식이 없으면 그대로 둔다."""
    armor = rules.get('armor')
    if armor is None or 'pierce_base' in armor:
        return rules
    return {**rules, 'armor': {**armor, 'save_target': None, 'pierce_base': PIERCE_BASE}}


def without_pierce(rules: dict) -> dict:
    """되돌릴 때. 방어 방식에서 세이브의 목표값과 관통의 기준값을 뺀다. 세이브 방식이었으면 방어 방식을 없앤다."""
    armor = rules.get('armor')
    if armor is None:
        return rules
    if armor.get('mode') == 'save':
        return {**rules, 'armor': None}
    kept = {key: value for key, value in armor.items() if key not in ('save_target', 'pierce_base')}
    return {**rules, 'armor': kept}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 읽어 바꿔 적는다. 바뀐 것만 적는다. 두 번 돌려도 결과가 같다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_pierce)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_pierce)
