"""resistances

Revision ID: c5e7a9b1d3f6
Revises: a3c5e7f9b1d4
Create Date: 2026-11-15 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c5e7a9b1d3f6'
down_revision: str | Sequence[str] | None = 'a3c5e7f9b1d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 저항(#886 ②). 테이블의 시트에 타고난 저항(resistances)을 둔다. 시트를 받을 때 시나리오의 시트에서 복사한다.
# 이미 있는 시트는 저항이 없다(빈 목록). 룰북과 시나리오의 칸(부상의 저항, 시트와 NPC 시트와 물건의 저항,
# 수치를 내리는 맞추기의 성질)은 비워도 되는 칸이라 올릴 때 고치지 않는다. 굳힌 판도 고치지 않는다.
# 되돌리면 시트의 칸을 지우고, 룰북과 시나리오에서 그 칸들을 뺀다(그때의 모양은 모르는 칸을 받지 않는다).
# 앱의 코드를 가져오지 않는다


def without_key(document: dict, key: str) -> dict:
    """문서 하나에서 그 칸을 뺀다."""
    return {name: value for name, value in document.items() if name != key}


def effects_without_nature(effects: list | None) -> list:
    """되돌릴 때. 효과들에서 맞추기의 성질을 뺀다."""
    return [without_key(effect, 'nature') for effect in effects or []]


def rules_without_resistances(rules: dict) -> dict:
    """되돌릴 때. 룰북의 규칙의 부상에서 저항을, 기술의 효과에서 성질을 뺀다."""
    changed = dict(rules)
    if 'injuries' in rules:
        changed['injuries'] = [without_key(injury, 'resistances') for injury in rules['injuries']]
    if 'skills' in rules:
        changed['skills'] = [with_plain_effects(skill) for skill in rules['skills']]
    return changed


def sheet_without_resistances(sheet: dict | None) -> dict | None:
    """되돌릴 때. 캐릭터의 시트 하나에서 저항을 뺀다. 시트가 없으면 그대로다."""
    return None if sheet is None else without_key(sheet, 'resistances')


def with_plain_effects(document: dict) -> dict:
    """되돌릴 때. 효과가 있는 문서(공격, 아이템 규칙)의 효과에서 성질을 뺀다. 효과의 칸이 없으면 그대로다."""
    if 'effects' not in document:
        return document
    return {**document, 'effects': effects_without_nature(document['effects'])}


def holder_without_resistances(holder: dict) -> dict:
    """되돌릴 때. NPC 시트나 몬스터 시트 하나에서 저항과 공격의 효과의 성질을 뺀다."""
    plain = without_key(holder, 'resistances')
    if 'attacks' not in holder:
        return plain
    return {**plain, 'attacks': [with_plain_effects(attack) for attack in holder['attacks'] or []]}


def item_without_resistances(rule: dict) -> dict:
    """되돌릴 때. 아이템 규칙 하나에서 저항과 효과의 성질을 뺀다."""
    return with_plain_effects(without_key(rule, 'resistances'))


def scenario_without_resistances(row: dict) -> dict:
    """되돌릴 때. 시나리오 한 줄의 문서 칸들에서 저항과 성질을 뺀다."""
    return {
        'default_sheet': sheet_without_resistances(row['default_sheet']),
        'pregens': [
            {**pregen, 'sheet': sheet_without_resistances(pregen.get('sheet'))} for pregen in row['pregens'] or []
        ],
        'npc_sheets': [holder_without_resistances(sheet) for sheet in row['npc_sheets'] or []],
        'monster_sheets': [holder_without_resistances(sheet) for sheet in row['monster_sheets'] or []],
        'items': [item_without_resistances(rule) for rule in row['items'] or []],
    }


SCENARIO_FIELDS = ('default_sheet', 'pregens', 'npc_sheets', 'monster_sheets', 'items')


def normalized(row) -> dict:
    """시나리오 한 줄의 문서 칸들. 목록 칸이 비어 있으면(NULL) 빈 목록으로 읽는다."""
    return {field: row[field] if field == 'default_sheet' else row[field] or [] for field in SCENARIO_FIELDS}


def rewrite_rulebooks(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 룰북의 규칙에서 저항과 성질을 뺀다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = rules_without_resistances(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def rewrite_scenarios(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 시트와 NPC 시트와 몬스터 시트와 아이템 규칙에서 저항과 성질을 뺀다."""
    columns = ', '.join(SCENARIO_FIELDS)
    for row in connection.execute(sa.text(f'SELECT asset_id, {columns} FROM scenarios')).mappings().all():
        before = normalized(row)
        changed = scenario_without_resistances(before)
        if changed != before:
            assignments = ', '.join(f'{field} = CAST(:{field} AS JSONB)' for field in SCENARIO_FIELDS)
            values = {field: json.dumps(value) for field, value in changed.items()}
            connection.execute(
                sa.text(f'UPDATE scenarios SET {assignments} WHERE asset_id = :id'), {**values, 'id': row['asset_id']}
            )


def upgrade() -> None:
    op.add_column(
        'table_sheets',
        sa.Column('resistances', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_table_sheets_resistances_is_array'), 'table_sheets', "jsonb_typeof(resistances) = 'array'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_sheets_resistances_is_array'), 'table_sheets', type_='check')
    op.drop_column('table_sheets', 'resistances')
    rewrite_scenarios(op.get_bind())
    rewrite_rulebooks(op.get_bind())
