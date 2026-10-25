"""thrown effects

Revision ID: e4a6c8d0f2b3
Revises: d2f4a6b8c0e1
Create Date: 2026-11-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e4a6c8d0f2b3'
down_revision: str | Sequence[str] | None = 'd2f4a6b8c0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모든 물건을 던진다(#801). 시나리오 초안의 아이템 규칙에서 던지는 판정의 피해(throw.harm)를 효과의 피해로 옮긴다.
# 이미 회복이나 피해의 효과가 있으면 옮기지 않고 버린다(한 물건에 HP 의 변화는 하나다).
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_62, 같은 모양).
# 앱의 코드를 가져오지 않는다


def with_throw_damage(rule: dict) -> dict:
    """아이템 규칙 하나. 던지는 판정의 피해를 효과로 옮긴다. 이미 옮겼으면 그대로다(두 번 돌려도 같다)."""
    thrown = rule.get('throw')
    if not thrown or 'harm' not in thrown:
        return rule
    effects = list(rule.get('effects', []))
    if not any(effect['kind'] in ('heal', 'damage') for effect in effects):
        effects = [{'kind': 'damage', 'magnitude': thrown['harm']}, *effects]
    kept = {key: value for key, value in thrown.items() if key != 'harm'}
    return {**rule, 'throw': kept, 'effects': effects}


def without_throw_damage(rule: dict) -> dict:
    """
    되돌릴 때. 던지는 판정에 효과의 피해를 피해(harm)로 되돌리고 그 효과를 뺀다.

    그때 던지는 판정은 피해와 함께였다. 피해가 없는 것(장비의 것도, 장비에는 효과가 없다)은 판정을 버린다.
    """
    thrown = rule.get('throw')
    if not thrown or 'harm' in thrown:
        return rule
    effects = rule.get('effects', [])
    damage = next((effect for effect in effects if effect['kind'] == 'damage'), None)
    if damage is None:
        return {**rule, 'throw': None}
    left = [effect for effect in effects if effect is not damage]
    return {**rule, 'throw': {**thrown, 'harm': damage['magnitude']}, 'effects': left}


def rewrite_items(connection: sa.Connection, step) -> None:
    """모든 시나리오의 아이템 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    scenarios = sa.table('scenarios', sa.column('asset_id'), sa.column('items', postgresql.JSONB))
    for scenario_id, rules in connection.execute(sa.select(scenarios.c.asset_id, scenarios.c['items'])).all():
        changed = [step(rule) for rule in rules or []]
        if changed != (rules or []):
            update = scenarios.update().where(scenarios.c.asset_id == scenario_id)
            connection.execute(update.values({scenarios.c['items']: changed}))


def upgrade() -> None:
    rewrite_items(op.get_bind(), with_throw_damage)


def downgrade() -> None:
    rewrite_items(op.get_bind(), without_throw_damage)
