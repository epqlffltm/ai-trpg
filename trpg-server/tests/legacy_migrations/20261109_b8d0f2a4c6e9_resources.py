"""resources

Revision ID: b8d0f2a4c6e9
Revises: a7c9e1b3d5f8
Create Date: 2026-11-09 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8d0f2a4c6e9'
down_revision: str | Sequence[str] | None = 'a7c9e1b3d5f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# HP 말고 다른 수치(#804). 룰북의 규칙에 수치들(resources)을 더하고, 시트에 지금 값(resources)을 둔다.
# 이미 있는 룰북은 수치가 없다(빈 목록). 템플릿의 예시(가벼운 규칙의 마나와 스태미나)는 새로 만드는 룰북에만 든다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_64, 같은 모양).
# 되돌리면 수치와 시트의 값을 지우고, 시나리오 초안의 아이템 규칙에서 맞추기(adjust)의 효과를 뺀다.
# 앱의 코드를 가져오지 않는다


def with_resources(rules: dict) -> dict:
    """룰북의 규칙. 수치가 없으면 빈 목록을 둔다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    return rules if 'resources' in rules else {**rules, 'resources': []}


def without_resources(rules: dict) -> dict:
    """되돌릴 때. 수치를 뺀다."""
    return {key: value for key, value in rules.items() if key != 'resources'}


def without_adjust(rule: dict) -> dict:
    """되돌릴 때. 아이템 규칙 하나의 효과에서 맞추기를 뺀다. 그때는 없던 효과다."""
    effects = rule.get('effects')
    if not effects:
        return rule
    return {**rule, 'effects': [effect for effect in effects if effect.get('kind') != 'adjust']}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def rewrite_items(connection: sa.Connection, step) -> None:
    """모든 시나리오의 아이템 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    scenarios = sa.table('scenarios', sa.column('asset_id'), sa.column('items', postgresql.JSONB))
    for scenario_id, rules in connection.execute(sa.select(scenarios.c.asset_id, scenarios.c['items'])).all():
        changed = [step(rule) for rule in rules or []]
        if changed != (rules or []):
            update = scenarios.update().where(scenarios.c.asset_id == scenario_id)
            connection.execute(update.values({scenarios.c['items']: changed}))


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_resources)
    op.add_column(
        'table_sheets',
        sa.Column('resources', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_table_sheets_resources_is_object'), 'table_sheets', "jsonb_typeof(resources) = 'object'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_sheets_resources_is_object'), 'table_sheets', type_='check')
    op.drop_column('table_sheets', 'resources')
    rewrite_items(op.get_bind(), without_adjust)
    rewrite_rulebooks(op.get_bind(), without_resources)
