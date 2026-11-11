"""injury minutes

Revision ID: be6f94759fa1
Revises: f2eb30d7461c
Create Date: 2026-10-15 16:03:54.247785

"""

import json
import math
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'be6f94759fa1'
down_revision: str | Sequence[str] | None = 'f2eb30d7461c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북의 규칙에서 오래 가는 부상과 치료의 기간을 라운드 수에서 게임 안의 분으로 옮긴다(판 형식 25).
# 판(시나리오의 판, 테이블의 복사본)은 고치지 않는다.
# 읽을 때 올려 읽는다(app/assets/scenarios/upgrades.py 의 upgrade_from_24).
# 룰북은 템플릿에서만 만든다. 지금의 SRD5 템플릿(app/engine/templates.py)과 같은 값을 여기에 적어 둔다.
# 앱의 코드를 가져오지 않는다. 템플릿이 나중에 바뀌어도 이 마이그레이션이 채운 값은 그대로다
DAY = 24 * 60
# 템플릿에 없는 부상이나 줄은 라운드 수에 이 분을 곱한다(새 시나리오의 라운드 하나의 기본 시간)
ROUND_MINUTES = 10

LASTING = {
    'broken_arm': {'heal_minutes': 14 * DAY, 'treat_minutes': 3 * DAY},
    'leg_wound': {'heal_minutes': 7 * DAY, 'treat_minutes': 2 * DAY},
}
# 치료 실패 표의 덧남. (낮은 눈, 높은 눈) 마다 늦춰지는 분
WORSEN = {(2, 10): 2 * DAY, (11, 30): DAY}

# 되돌릴 때 쓰는 옛 SRD5 의 라운드 수
OLD_LASTING = {
    'broken_arm': {'rounds': 30, 'treat_rounds': 10},
    'leg_wound': {'rounds': 20, 'treat_rounds': 10},
}
OLD_WORSEN = {(2, 10): 10, (11, 30): 5}


def rounds_of(minutes: int) -> int:
    """분을 라운드 수로(되돌릴 때). 기본 걸음으로 나누어 올린다. 적어도 1 이다."""
    return max(1, math.ceil(minutes / ROUND_MINUTES))


def injury_to_minutes(injury: dict) -> dict:
    """
    부상 하나의 기간을 분으로. 오래 가는 것은 템플릿의 값, 템플릿에 없으면 라운드 × 10분이다.

    짧은 것과 결손은 기간이 그대로이고 치료의 칸이 없다. 이미 분으로 적힌 것은 그대로 둔다.
    """
    upgraded = {key: value for key, value in injury.items() if key != 'treat_rounds'}
    if injury.get('healing') != 'heals':
        return {**upgraded, 'heal_minutes': None, 'treat_minutes': None}
    if injury.get('heal_minutes') is not None:
        return upgraded
    known = LASTING.get(injury['key'], {})
    rounds = injury.get('rounds') or 1
    upgraded['rounds'] = None
    upgraded['heal_minutes'] = known.get('heal_minutes', rounds * ROUND_MINUTES)
    treat_rounds = injury.get('treat_rounds')
    if injury.get('treat_difficulty') is None or treat_rounds is None:
        upgraded['treat_difficulty'] = None
        upgraded['treat_minutes'] = None
    else:
        upgraded['treat_minutes'] = known.get('treat_minutes', treat_rounds * ROUND_MINUTES)
    return upgraded


def injury_to_rounds(injury: dict) -> dict:
    """되돌릴 때. 부상 하나의 기간을 라운드 수로. 템플릿의 부상은 옛 값, 아니면 분 ÷ 10 을 올린 것이다."""
    downgraded = {key: value for key, value in injury.items() if key not in ('heal_minutes', 'treat_minutes')}
    heal_minutes = injury.get('heal_minutes')
    treat_minutes = injury.get('treat_minutes')
    if injury.get('healing') != 'heals' or heal_minutes is None:
        return {**downgraded, 'treat_rounds': None}
    old = OLD_LASTING.get(injury['key'], {})
    downgraded['rounds'] = old.get('rounds', rounds_of(heal_minutes))
    downgraded['treat_rounds'] = None if treat_minutes is None else old.get('treat_rounds', rounds_of(treat_minutes))
    return downgraded


def row_to_minutes(row: dict) -> dict:
    """치료 실패 표의 한 줄. 덧남이면 늦춰지는 분을 적는다. 이미 분으로 적힌 것은 그대로 둔다."""
    upgraded = {key: value for key, value in row.items() if key != 'rounds'}
    if row.get('kind') != 'worsen':
        return {**upgraded, 'delay_minutes': None}
    if row.get('delay_minutes') is not None:
        return upgraded
    upgraded['delay_minutes'] = WORSEN.get((row['low'], row['high']), (row.get('rounds') or 1) * ROUND_MINUTES)
    return upgraded


def row_to_rounds(row: dict) -> dict:
    """되돌릴 때. 치료 실패 표의 한 줄의 덧남을 라운드 수로."""
    downgraded = {key: value for key, value in row.items() if key != 'delay_minutes'}
    delay = row.get('delay_minutes')
    if row.get('kind') != 'worsen' or delay is None:
        return {**downgraded, 'rounds': None}
    downgraded['rounds'] = OLD_WORSEN.get((row['low'], row['high']), rounds_of(delay))
    return downgraded


def convert(rules: dict, injury_step, row_step) -> dict:
    """규칙 하나의 부상들과 치료 실패 표를 바꾼다. 없는 칸은 그대로 둔다."""
    converted = dict(rules)
    if converted.get('injuries') is not None:
        converted['injuries'] = [injury_step(injury) for injury in converted['injuries']]
    treatment = converted.get('treatment')
    if treatment is not None:
        rows = [row_step(row) for row in treatment['mishaps']['rows']]
        converted['treatment'] = {**treatment, 'mishaps': {**treatment['mishaps'], 'rows': rows}}
    return converted


def rewrite_rulebooks(connection: sa.Connection, injury_step, row_step) -> None:
    """모든 룰북의 규칙을 읽어 바꿔 적는다. 바뀐 것만 적는다. 두 번 돌려도 결과가 같다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        converted = convert(rules, injury_step, row_step)
        if converted != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(converted), 'id': rulebook_id},
            )


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), injury_to_minutes, row_to_minutes)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), injury_to_rounds, row_to_rounds)
