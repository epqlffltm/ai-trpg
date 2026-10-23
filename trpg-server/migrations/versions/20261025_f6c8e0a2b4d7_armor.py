"""armor

Revision ID: f6c8e0a2b4d7
Revises: e5b7d9f1a3c6
Create Date: 2026-10-25 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6c8e0a2b4d7'
down_revision: str | Sequence[str] | None = 'e5b7d9f1a3c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장비가 공격과 방어에 든다(#276). 룰북의 규칙에 방어 방식(armor)과 칸이 맞을 가중치(hit_weight)를 더한다.
# 옛 룰북은 방어 방식이 없는 것(null, 방어구가 막지 않는다)으로, 칸의 가중치는 1 로 둔다. 템플릿의 방식을 채우지 않는다.
# 판은 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_47). 앱의 코드를 가져오지 않는다


def weighted(slot: dict) -> dict:
    """가중치가 없는 칸에 1 을 더한다. 이미 있으면 그대로 둔다."""
    return slot if 'hit_weight' in slot else {**slot, 'hit_weight': 1}


def with_armor(rules: dict) -> dict:
    """방어 방식이 없는 규칙에 null 을 더하고, 칸마다 가중치를 채운다. 이미 있으면 그대로 둔다."""
    slots = [weighted(slot) for slot in rules.get('equipment_slots', [])]
    return {**rules, 'equipment_slots': slots, 'armor': rules.get('armor')}


def without_armor(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 방어 방식과 칸의 가중치를 뺀다."""
    slots = [
        {key: value for key, value in slot.items() if key != 'hit_weight'} for slot in rules.get('equipment_slots', [])
    ]
    kept = {key: value for key, value in rules.items() if key != 'armor'}
    return {**kept, 'equipment_slots': slots}


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
    rewrite_rulebooks(op.get_bind(), with_armor)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_armor)
