"""skills

Revision ID: e1a3c5d7f9b2
Revises: d0f2b4c6e8a1
Create Date: 2026-11-12 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e1a3c5d7f9b2'
down_revision: str | Sequence[str] | None = 'd0f2b4c6e8a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 기술과 주문(#805). 룰북의 규칙에 기술들(skills)을 더하고, 테이블의 시트에 아는 기술(skills)을 둔다.
# 이미 있는 룰북은 기술이 없다(빈 목록).
# 템플릿의 예시(가벼운 규칙의 치유의 손길과 정신 집중)는 새로 만드는 룰북에만 든다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_65, 같은 모양).
# 시나리오의 시트(기본 시트, 프리젠의 시트)의 아는 기술은 비어 있는 것이 기본이라 고치지 않는다.
# 부상이 기술의 효과로도 생긴다(source 'skill').
# 되돌리면 기술과 아는 기술과 기술로 생긴 부상을 지우고, 기술을 쓰는 선언의 행동을 비운다(그때는 없던 행동이다).
# 앱의 코드를 가져오지 않는다

SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill')"
OLD_SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource')"


def with_skills(rules: dict) -> dict:
    """룰북의 규칙. 기술이 없으면 빈 목록을 둔다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    return rules if 'skills' in rules else {**rules, 'skills': []}


def without_skills(rules: dict) -> dict:
    """되돌릴 때. 기술을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'skills'}


def without_known(sheet: dict | None) -> dict | None:
    """되돌릴 때. 시나리오의 시트 하나에서 아는 기술을 뺀다. 시트가 없으면 그대로다."""
    if sheet is None:
        return None
    return {key: value for key, value in sheet.items() if key != 'skills'}


def pregens_without_known(pregens: list[dict] | None) -> list[dict]:
    """되돌릴 때. 프리젠마다 시트의 아는 기술을 뺀다."""
    return [{**pregen, 'sheet': without_known(pregen.get('sheet'))} for pregen in pregens or []]


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def rewrite_scenario_sheets(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 기본 시트와 프리젠의 시트에서 아는 기술을 뺀다. 바뀐 것만 적는다."""
    rows = connection.execute(sa.text('SELECT asset_id, default_sheet, pregens FROM scenarios')).all()
    for scenario_id, default_sheet, pregens in rows:
        sheet, others = without_known(default_sheet), pregens_without_known(pregens)
        if sheet != default_sheet or others != (pregens or []):
            connection.execute(
                sa.text(
                    'UPDATE scenarios SET default_sheet = CAST(:sheet AS JSONB), pregens = CAST(:pregens AS JSONB) '
                    'WHERE asset_id = :id'
                ),
                {'sheet': json.dumps(sheet), 'pregens': json.dumps(others), 'id': scenario_id},
            )


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_skills)
    op.add_column(
        'table_sheets',
        sa.Column('skills', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_table_sheets_skills_is_array'), 'table_sheets', "jsonb_typeof(skills) = 'array'"
    )
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', SOURCES)


def downgrade() -> None:
    op.execute("UPDATE round_declarations SET action = NULL WHERE action->>'kind' = 'skill'")
    # 기술로 생긴 부상은 되돌린 모양에 들어갈 자리가 없다. 지운다
    op.execute("DELETE FROM table_injuries WHERE source = 'skill'")
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', OLD_SOURCES)
    op.drop_constraint(op.f('ck_table_sheets_skills_is_array'), 'table_sheets', type_='check')
    op.drop_column('table_sheets', 'skills')
    rewrite_scenario_sheets(op.get_bind())
    rewrite_rulebooks(op.get_bind(), without_skills)
