"""attack effects

Revision ID: f2b4d6e8a0c3
Revises: e1a3c5d7f9b2
Create Date: 2026-11-13 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2b4d6e8a0c3'
down_revision: str | Sequence[str] | None = 'e1a3c5d7f9b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 몬스터와 인물의 공격의 효과(#805 ③-b). 부상이 공격의 효과로도 생긴다(source 'attack').
# 공격의 효과와 비울 수 있는 피해 등급은 시나리오의 문서 칸(JSONB)과 굳힌 판에 있다. 비워도 되는 칸이라 고치지 않는다.
# 되돌리면 공격으로 생긴 부상을 지운다. 되돌린 모양에는 그 출처가 없다.
# 시나리오의 시트(monster_sheets, npc_sheets)의 공격에서 효과를 빼고, 피해 등급이 없는 공격(효과만 있던 것)은 지운다.
# 굳힌 판은 고치지 않는다(되돌린 코드는 그 판을 읽지 못한다. 되돌린 뒤에 게시한 판만 읽는다).
# 앱의 코드를 가져오지 않는다

SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill', 'attack')"
OLD_SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill')"


def without_effects(attacks: list[dict] | None) -> list[dict]:
    """되돌릴 때. 공격들에서 효과를 빼고, 피해 등급이 없는 공격은 지운다."""
    return [
        {key: value for key, value in attack.items() if key != 'effects'}
        for attack in attacks or []
        if attack.get('harm') is not None
    ]


def sheets_without_effects(sheets: list[dict] | None) -> list[dict]:
    """되돌릴 때. 시트마다 공격을 without_effects 로 바꾼다. 공격이 없는 시트는 그대로다."""
    return [
        {**sheet, 'attacks': without_effects(sheet['attacks'])} if 'attacks' in sheet else sheet
        for sheet in sheets or []
    ]


def rewrite_scenario_attacks(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 몬스터 시트와 NPC 시트의 공격을 고쳐 쓴다. 바뀐 것만 적는다."""
    rows = connection.execute(sa.text('SELECT asset_id, monster_sheets, npc_sheets FROM scenarios')).all()
    for scenario_id, monster_sheets, npc_sheets in rows:
        monsters, people = sheets_without_effects(monster_sheets), sheets_without_effects(npc_sheets)
        if monsters != (monster_sheets or []) or people != (npc_sheets or []):
            connection.execute(
                sa.text(
                    'UPDATE scenarios SET monster_sheets = CAST(:monsters AS JSONB), '
                    'npc_sheets = CAST(:people AS JSONB) WHERE asset_id = :id'
                ),
                {'monsters': json.dumps(monsters), 'people': json.dumps(people), 'id': scenario_id},
            )


def upgrade() -> None:
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', SOURCES)


def downgrade() -> None:
    op.execute("DELETE FROM table_injuries WHERE source = 'attack'")
    rewrite_scenario_attacks(op.get_bind())
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', OLD_SOURCES)
