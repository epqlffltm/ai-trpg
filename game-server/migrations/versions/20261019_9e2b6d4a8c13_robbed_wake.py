"""robbed wake

Revision ID: 9e2b6d4a8c13
Revises: 7c3e5a9f1d48
Create Date: 2026-10-19 23:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9e2b6d4a8c13'
down_revision: str | Sequence[str] | None = '7c3e5a9f1d48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북의 규칙에 빼앗긴 NPC 가 깨어날 때의 반응(robbed_wake)을 채운다(판 형식 40). 판은 읽을 때 올린다
# (app/assets/scenarios/upgrades.py 의 upgrade_from_39). 지금의 SRD5 템플릿과 같은 값을 여기에 적어 둔다.
# 앱의 코드를 가져오지 않는다. 템플릿이 나중에 바뀌어도 이 마이그레이션이 채운 값은 그대로다
ROBBED_WAKE = {'hostile': 10, 'wary': 40}

# 태도의 값들. 경계(wary)가 더해졌다
ATTITUDES_BEFORE = "attitude IN ('friendly', 'neutral', 'hostile')"
ATTITUDES_AFTER = "attitude IN ('friendly', 'neutral', 'wary', 'hostile')"


def with_robbed_wake(rules: dict) -> dict:
    """깨어날 때의 반응이 없는 규칙에 SRD5 의 것을 더한다. 이미 있으면 그대로 둔다."""
    if 'robbed_wake' in rules:
        return rules
    return {**rules, 'robbed_wake': ROBBED_WAKE}


def without_robbed_wake(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 깨어날 때의 반응을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'robbed_wake'}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 읽어 바꿔 적는다. 바뀐 것만 적는다. 두 번 돌려도 결과가 같다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def replace_attitude_check(condition: str) -> None:
    """태도의 CHECK 를 새 조건으로 바꾼다."""
    op.drop_constraint(op.f('ck_table_npcs_attitude_allowed'), 'table_npcs', type_='check')
    op.create_check_constraint(op.f('ck_table_npcs_attitude_allowed'), 'table_npcs', condition)


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_robbed_wake)
    replace_attitude_check(ATTITUDES_AFTER)
    # 쓰러져 있는 동안 처음 빼앗긴 라운드. 깨어날 때 반응을 굴리고 비운다
    op.add_column('table_npcs', sa.Column('robbed_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_npcs_robbed_round_positive'), 'table_npcs', 'robbed_round IS NULL OR robbed_round >= 1'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_npcs_robbed_round_positive'), 'table_npcs', type_='check')
    op.drop_column('table_npcs', 'robbed_round')
    # 경계하던 인물은 중립으로 돌린다. 옛 CHECK 가 경계를 받지 않는다
    op.execute("UPDATE table_npcs SET attitude = 'neutral' WHERE attitude = 'wary'")
    replace_attitude_check(ATTITUDES_BEFORE)
    rewrite_rulebooks(op.get_bind(), without_robbed_wake)
