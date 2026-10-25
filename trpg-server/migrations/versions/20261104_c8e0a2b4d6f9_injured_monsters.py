"""injured monsters

Revision ID: c8e0a2b4d6f9
Revises: b6e8a0c2d4f7
Create Date: 2026-11-04 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e0a2b4d6f9'
down_revision: str | Sequence[str] | None = 'b6e8a0c2d4f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 몬스터도 부상을 입는다(#799). 부상의 주인에 몬스터 한 마리를 더한다. 주인은 캐릭터, NPC, 몬스터 중 정확히 하나다.
# 룰북의 부상에 성질(natures)을 더한다. 룰북은 템플릿에서만 만들고 부상은 고칠 수 없으니(방어 규칙만 고친다),
# 그 룰북의 템플릿(rules.template)에 같은 이름표의 부상이 있으면 템플릿의 성질을,
# 없으면 빈 성질(누구나 입는다)을 채운다.
# 아래의 표는 지금의 템플릿(app/engine/templates/*.json)과 같은 값이다. 앱의 코드를 가져오지 않는다.
# 게시한 판은 그때의 규칙으로 굳어 있어 성질을 비운다(app/assets/scenarios/upgrades.py 의 upgrade_from_60)

ONE_HOLDER = 'num_nonnulls(sheet_id, npc_entry_id, monster_id) = 1'
OLD_ONE_HOLDER = '(sheet_id IS NULL) <> (npc_entry_id IS NULL)'

BODY = ['body']
MIND = ['mind']
TEMPLATE_NATURES: dict[str, dict[str, list[str]]] = {
    'srd5': {
        'stunned': ['stun'],
        'poisoned': ['poison'],
        'blinded': ['sense'],
        'deafened': ['sense'],
        'broken_arm': BODY,
        'leg_wound': BODY,
        'lost_left_hand': BODY,
        'lost_right_hand': BODY,
        'lost_eye': BODY,
        'deep_scar': BODY,
        'crooked_arm': BODY,
        'limp': BODY,
    },
    'horror': {
        'panicked': MIND,
        'stunned': ['stun'],
        'shaken': MIND,
        'bleeding': BODY,
        'deep_cut': BODY,
        'broken_leg': BODY,
        'nightmares': MIND,
        'lost_fingers': BODY,
        'lost_eye': BODY,
        'scar': BODY,
        'limp': BODY,
        'haunted': MIND,
    },
}


def with_natures(rules: dict) -> dict:
    """성질이 없는 부상에 템플릿의 성질(없으면 빈 성질)을 더한다. 이미 있으면 그대로 둔다."""
    known = TEMPLATE_NATURES.get(rules.get('template'), {})
    injuries = [with_nature(injury, known) for injury in rules.get('injuries', [])]
    return {**rules, 'injuries': injuries}


def with_nature(injury: dict, known: dict[str, list[str]]) -> dict:
    """부상 하나. 성질이 없으면 템플릿의 같은 이름표의 성질을 채운다. 사본마다 새 목록이다."""
    if 'natures' in injury:
        return injury
    return {**injury, 'natures': list(known.get(injury.get('key'), []))}


def without_natures(rules: dict) -> dict:
    """되돌릴 때. 부상에서 성질을 뺀다."""
    injuries = [without_key(injury, 'natures') for injury in rules.get('injuries', [])]
    return {**rules, 'injuries': injuries}


def without_key(document: dict, key: str) -> dict:
    """그 칸을 뺀 사본."""
    return {name: value for name, value in document.items() if name != key}


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
    op.add_column('table_injuries', sa.Column('monster_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f('fk_table_injuries_monster_id_table_monsters'),
        'table_injuries',
        'table_monsters',
        ['monster_id'],
        ['id'],
        ondelete='CASCADE',
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표의 CHECK 가 바뀐 것을 찾지 못한다
    op.drop_constraint(op.f('ck_table_injuries_one_holder'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_one_holder'), 'table_injuries', ONE_HOLDER)
    rewrite_rulebooks(op.get_bind(), with_natures)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_natures)
    # 몬스터의 부상은 되돌린 모양에 들어갈 자리가 없다. 지운다
    op.execute('DELETE FROM table_injuries WHERE monster_id IS NOT NULL')
    op.drop_constraint(op.f('ck_table_injuries_one_holder'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_one_holder'), 'table_injuries', OLD_ONE_HOLDER)
    op.drop_constraint(op.f('fk_table_injuries_monster_id_table_monsters'), 'table_injuries', type_='foreignkey')
    op.drop_column('table_injuries', 'monster_id')
