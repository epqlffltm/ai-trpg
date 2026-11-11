"""check rolls

Revision ID: 9b2d4f6a8c10
Revises: 7c3e9a1f5b20
Create Date: 2026-12-06 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9b2d4f6a8c10'
down_revision: str | Sequence[str] | None = '7c3e9a1f5b20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 판정 방식(#404). 룰북의 규칙에 굴림(roll: 주사위의 개수, 성공을 가르는 쪽, 난이도마다 기량에 더하는 값)을 더한다.
# 이미 있는 룰북은 주사위 하나를 굴려 눈 + 보정 ≥ 목표로 가르던 규칙이다. 하던 대로 돈다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_68, 같은 값).
# 되돌리면 룰북의 규칙에서 굴림을 뺀다(그때의 모양은 모르는 칸을 받지 않는다). 앱의 코드를 가져오지 않는다
# 되돌리기 전에 under 나 주사위 여럿으로 바꾼 룰북이 있으면, 되돌린 뒤에는 주사위 하나의 over 로 돈다

ROLL = {'count': 1, 'style': 'over', 'shifts': {}}


def with_roll(rules: dict) -> dict:
    """룰북의 규칙. 굴림이 없으면 주사위 하나의 over 로 채운다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    return rules if 'roll' in rules else {**rules, 'roll': ROLL}


def without_roll(rules: dict) -> dict:
    """되돌릴 때. 룰북의 규칙에서 굴림을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'roll'}


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
    rewrite_rulebooks(op.get_bind(), with_roll)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_roll)
