"""steal

Revision ID: 8b4f2d6e9a71
Revises: 5d2c8e7a1f34
Create Date: 2026-10-19 15:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8b4f2d6e9a71'
down_revision: str | Sequence[str] | None = '5d2c8e7a1f34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북의 규칙에 훔치기(steal)를 채운다(판 형식 36). 판(시나리오의 판, 테이블의 복사본)은 고치지 않는다.
# 읽을 때 올려 읽는다(app/assets/scenarios/upgrades.py 의 upgrade_from_35).
# 룰북은 템플릿에서만 만든다. 지금의 SRD5 템플릿(app/engine/templates.py)과 같은 값을 여기에 적어 둔다.
# 앱의 코드를 가져오지 않는다. 템플릿이 나중에 바뀌어도 이 마이그레이션이 채운 값은 그대로다
STEAL = {
    'ability': 'dex',
    'difficulty': 'medium',
    'awareness': 'wis',
    'equipped': 5,
    'rarity_step': 2,
    'dull_kinds': [{'kind': 'undead', 'amount': 3}, {'kind': 'construct', 'amount': 3}],
    'dull': 3,
    'unwary': 3,
    'distracted': 2,
}


def with_steal(rules: dict) -> dict:
    """훔치기가 없는 규칙에 SRD5 의 훔치기를 더한다. 이미 있으면 그대로 둔다."""
    if 'steal' in rules:
        return rules
    return {**rules, 'steal': STEAL}


def without_steal(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 훔치기를 뺀다."""
    return {key: value for key, value in rules.items() if key != 'steal'}


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
    rewrite_rulebooks(op.get_bind(), with_steal)
    # 마리가 처음 싸운 라운드(치거나 맞거나 훔치다 들켰다). 비어 있으면 아직 싸우지 않았다(훔치기가 쉽다)
    op.add_column('table_monsters', sa.Column('fought_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_monsters_fought_round_positive'), 'table_monsters', 'fought_round IS NULL OR fought_round >= 1'
    )
    # 이미 진행 중인 테이블의 마리는 만난 라운드에 싸운 것으로 본다. 만나면 차례마다 치기 때문이다
    op.execute('UPDATE table_monsters SET fought_round = engaged_round WHERE engaged_round IS NOT NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_monsters_fought_round_positive'), 'table_monsters', type_='check')
    op.drop_column('table_monsters', 'fought_round')
    rewrite_rulebooks(op.get_bind(), without_steal)
