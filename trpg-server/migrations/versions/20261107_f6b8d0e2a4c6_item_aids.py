"""item aids

Revision ID: f6b8d0e2a4c6
Revises: e4a6c8d0f2b3
Create Date: 2026-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f6b8d0e2a4c6'
down_revision: str | Sequence[str] | None = 'e4a6c8d0f2b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 물건이 다른 행동을 거든다(#802). 시나리오 초안에서
#   - 아이템 규칙의 치료 보정(treat_bonus)을 치료의 거들기(늘 없어짐)로 옮긴다.
#   - 길의 따기·고치기와 자물쇠 물건의 따기의 특정 도구(tool)를 도구가 있어야 하는가(needs_tool)로 바꾸고,
#     그 도구의 아이템 규칙에 그 행동의 거들기(보정 0, 안 없어짐)를 더한다. 규칙이 없던 물건이면 장비의 규칙을 더한다.
#     아이템 규칙이 이미 가득(100)이면 더하지 못한다. 그 문은 거드는 물건이 없어 게시할 때 알린다(route_tool_missing).
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_63, 같은 모양).
# 앱의 코드를 가져오지 않는다

# 시나리오 하나의 아이템 규칙의 수(app/assets/models.py 의 SCENARIO_MAX_ITEM_RULES)
MAX_ITEM_RULES = 100


def with_treat_aid(rule: dict) -> dict:
    """아이템 규칙 하나의 치료 보정을 치료의 거들기로 옮긴다."""
    moved = {key: value for key, value in rule.items() if key != 'treat_bonus'}
    aids = list(rule.get('aids', []))
    if rule.get('treat_bonus') is not None:
        aids.append({'act': 'treat', 'bonus': rule['treat_bonus'], 'wear': 'always'})
    return {**moved, 'aids': aids}


def without_treat_aid(rule: dict) -> dict:
    """
    되돌릴 때. 치료의 거들기를 치료 보정으로 되돌리고 거들기를 뺀다.

    그때 치료 보정은 소모품에만, 1 이상이었다. 아니면 버린다. 다른 행동의 거들기도 버린다.
    """
    moved = {key: value for key, value in rule.items() if key != 'aids'}
    treat = next((aid for aid in rule.get('aids', []) if aid['act'] == 'treat'), None)
    usable = treat is not None and treat.get('bonus', 0) >= 1 and rule.get('kind') == 'consumable'
    return {**moved, 'treat_bonus': treat['bonus'] if usable else None}


def with_needs_tool(check: dict | None) -> dict | None:
    """따거나 고치는 판정 하나의 특정 도구를 도구가 있어야 하는가로 바꾼다."""
    if check is None:
        return None
    kept = {key: value for key, value in check.items() if key != 'tool'}
    return {**kept, 'needs_tool': check.get('tool') is not None}


def with_tool(check: dict | None, tool: str | None) -> dict | None:
    """되돌릴 때. 도구가 있어야 하는 판정에 그 행동을 거들던 물건 하나를 특정 도구로 적는다. 없으면 도구 없이."""
    if check is None:
        return None
    kept = {key: value for key, value in check.items() if key != 'needs_tool'}
    return {**kept, 'tool': tool if check.get('needs_tool') else None}


def old_tools(routes: list[dict], rules: list[dict]) -> list[tuple[str, str]]:
    """옛 모양의 도구들. (행동, 물건 항목)이다. 길의 따기, 자물쇠 물건의 따기, 길의 고치기의 차례다."""
    picks = [(route.get('lock') or {}).get('pick') for route in routes]
    picks += [(rule.get('lock') or {}).get('pick') for rule in rules]
    repairs = [route.get('repair') for route in routes]
    found = [('pick', check) for check in picks] + [('repair', check) for check in repairs]
    return [(act, check['tool']) for act, check in found if check and check.get('tool') is not None]


def with_tool_aid(rules: list[dict], act: str, tool: str) -> list[dict]:
    """그 도구의 아이템 규칙에 그 행동의 거들기를 더한다. 규칙이 없으면 장비의 규칙을 더한다(가득이면 못 한다)."""
    aid = {'act': act, 'bonus': 0, 'wear': 'never'}
    rule = next((one for one in rules if one['entry_id'] == tool), None)
    if rule is None:
        added = {'entry_id': tool, 'kind': 'gear', 'aids': [aid]}
        return [*rules, added] if len(rules) < MAX_ITEM_RULES else rules
    if any(one['act'] == act for one in rule.get('aids', [])):
        return rules
    return [{**one, 'aids': [*one.get('aids', []), aid]} if one is rule else one for one in rules]


def first_aid_item(rules: list[dict], act: str) -> str | None:
    """되돌릴 때. 그 행동을 거드는 첫 물건 항목. 없으면 None."""
    return next((rule['entry_id'] for rule in rules for aid in rule.get('aids', []) if aid['act'] == act), None)


def upgraded(routes: list[dict], rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """한 시나리오의 길과 아이템 규칙을 새 모양으로 바꾼다."""
    moved = [with_treat_aid(rule) for rule in rules]
    for act, tool in old_tools(routes, moved):
        moved = with_tool_aid(moved, act, tool)
    moved = [
        {**rule, 'lock': {**rule['lock'], 'pick': with_needs_tool(rule['lock'].get('pick'))}}
        if rule.get('lock')
        else rule
        for rule in moved
    ]
    lifted = [
        {**route, 'lock': {**route['lock'], 'pick': with_needs_tool(route['lock'].get('pick'))}}
        if route.get('lock')
        else route
        for route in routes
    ]
    lifted = [{**route, 'repair': with_needs_tool(route.get('repair'))} for route in lifted]
    return lifted, moved


def downgraded(routes: list[dict], rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """한 시나리오의 길과 아이템 규칙을 옛 모양으로 되돌린다."""
    pick, repair = first_aid_item(rules, 'pick'), first_aid_item(rules, 'repair')
    lowered = [
        {**route, 'lock': {**route['lock'], 'pick': with_tool(route['lock'].get('pick'), pick)}}
        if route.get('lock')
        else route
        for route in routes
    ]
    lowered = [{**route, 'repair': with_tool(route.get('repair'), repair)} for route in lowered]
    moved = [
        {**rule, 'lock': {**rule['lock'], 'pick': with_tool(rule['lock'].get('pick'), pick)}}
        if rule.get('lock')
        else rule
        for rule in rules
    ]
    return lowered, [without_treat_aid(rule) for rule in moved]


def rewrite(connection: sa.Connection, step) -> None:
    """모든 시나리오의 길과 아이템 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    scenarios = sa.table(
        'scenarios', sa.column('asset_id'), sa.column('items', postgresql.JSONB), sa.column('routes', postgresql.JSONB)
    )
    query = sa.select(scenarios.c.asset_id, scenarios.c['items'], scenarios.c.routes)
    for scenario_id, rules, routes in connection.execute(query).all():
        new_routes, new_rules = step(routes or [], rules or [])
        if (new_routes, new_rules) != (routes or [], rules or []):
            update = scenarios.update().where(scenarios.c.asset_id == scenario_id)
            connection.execute(update.values({scenarios.c['items']: new_rules, scenarios.c.routes: new_routes}))


def upgrade() -> None:
    rewrite(op.get_bind(), upgraded)


def downgrade() -> None:
    rewrite(op.get_bind(), downgraded)
