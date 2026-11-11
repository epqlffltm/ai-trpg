"""item effects

Revision ID: d2f4a6b8c0e1
Revises: c8e0a2b4d6f9
Create Date: 2026-11-05 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd2f4a6b8c0e1'
down_revision: str | Sequence[str] | None = 'c8e0a2b4d6f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 소모품의 효과 목록(#800). 시나리오 초안의 아이템 규칙에서 회복의 양(heals)과 푸는 부상(cures)을 효과로 옮긴다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_61, 같은 모양).
# 룰북에 물건을 인물이나 몬스터에게 쓸 때 맞히는 판정(item_check)을 더한다. 룰북은 템플릿에서만 만들고
# 그 칸은 고칠 수 없으니, 그 룰북의 템플릿의 값을 채운다(아래의 표는 지금의 템플릿과 같다). 모르는 템플릿은 없음이다.
# 부상이 물건의 효과로도 생긴다(source 'item'). 앱의 코드를 가져오지 않는다

ITEM_CHECKS: dict[str, dict] = {
    'srd5': {'ability': 'dex', 'difficulty': 'medium'},
    'horror': {'ability': 'agility', 'difficulty': 'medium'},
    'light': {'ability': 'body', 'difficulty': 'medium'},
}
SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item')"
OLD_SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath')"


def effects_of(rule: dict) -> list[dict]:
    """옛 아이템 규칙의 heals 와 cures 를 효과 목록으로. 회복 다음 풀기다(그때의 차례)."""
    effects = []
    if rule.get('heals') is not None:
        effects.append({'kind': 'heal', 'magnitude': rule['heals']})
    if rule.get('cures'):
        effects.append({'kind': 'cure', 'injuries': list(rule['cures'])})
    return effects


def with_effects(rule: dict) -> dict:
    """아이템 규칙 하나. 이미 효과 목록이 있으면 그대로다(두 번 돌려도 같다)."""
    if 'effects' in rule:
        return rule
    kept = {key: value for key, value in rule.items() if key not in ('heals', 'cures')}
    return {**kept, 'effects': effects_of(rule)}


def without_effects(rule: dict) -> dict:
    """되돌릴 때. 회복과 풀기를 heals 와 cures 로 되돌린다. 그때 없던 피해와 부상은 버린다."""
    if 'effects' not in rule:
        return rule
    effects = rule['effects']
    heal = next((effect['magnitude'] for effect in effects if effect['kind'] == 'heal'), None)
    cures = next((effect['injuries'] for effect in effects if effect['kind'] == 'cure'), [])
    kept = {key: value for key, value in rule.items() if key != 'effects'}
    return {**kept, 'heals': heal, 'cures': cures}


def with_item_check(rules: dict) -> dict:
    """룰북의 규칙. 맞히는 판정이 없으면 그 템플릿의 것을 채운다. 이미 있으면 그대로다."""
    if 'item_check' in rules:
        return rules
    known = ITEM_CHECKS.get(rules.get('template'))
    return {**rules, 'item_check': dict(known) if known else None}


def without_item_check(rules: dict) -> dict:
    """되돌릴 때. 맞히는 판정을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'item_check'}


def rewrite_items(connection: sa.Connection, step) -> None:
    """모든 시나리오의 아이템 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    scenarios = sa.table('scenarios', sa.column('asset_id'), sa.column('items', postgresql.JSONB))
    for scenario_id, rules in connection.execute(sa.select(scenarios.c.asset_id, scenarios.c['items'])).all():
        changed = [step(rule) for rule in rules or []]
        if changed != (rules or []):
            update = scenarios.update().where(scenarios.c.asset_id == scenario_id)
            connection.execute(update.values({scenarios.c['items']: changed}))


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
    rewrite_items(op.get_bind(), with_effects)
    rewrite_rulebooks(op.get_bind(), with_item_check)
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', SOURCES)


def downgrade() -> None:
    # 물건으로 생긴 부상은 되돌린 모양에 들어갈 자리가 없다. 지운다
    op.execute("DELETE FROM table_injuries WHERE source = 'item'")
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', OLD_SOURCES)
    rewrite_rulebooks(op.get_bind(), without_item_check)
    rewrite_items(op.get_bind(), without_effects)
