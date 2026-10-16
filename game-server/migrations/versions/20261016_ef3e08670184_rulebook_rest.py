"""rulebook rest

Revision ID: ef3e08670184
Revises: 64ab661f4014
Create Date: 2026-10-16 01:34:32.183452

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'ef3e08670184'
down_revision: str | Sequence[str] | None = '64ab661f4014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북의 규칙에 쉬기(rest)를 채운다(판 형식 28). 판(시나리오의 판, 테이블의 복사본)은 고치지 않는다.
# 읽을 때 올려 읽는다(app/assets/scenarios/upgrades.py 의 upgrade_from_27).
# 룰북은 템플릿에서만 만든다. 지금의 SRD5 템플릿(app/engine/templates.py)과 같은 값을 여기에 적어 둔다.
# 앱의 코드를 가져오지 않는다. 템플릿이 나중에 바뀌어도 이 마이그레이션이 채운 값은 그대로다
REST = {
    'short': {'minutes': 60, 'heal': 'moderate'},
    'long': {'minutes': 8 * 60},
    'revive': {'minutes': 8 * 60, 'target': 10},
    'natural': None,
}


def with_rest(rules: dict) -> dict:
    """쉬기가 없는 규칙에 SRD5 의 쉬기를 더한다. 이미 있으면 그대로 둔다."""
    if 'rest' in rules:
        return rules
    return {**rules, 'rest': REST}


def without_rest(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 쉬기를 뺀다."""
    return {key: value for key, value in rules.items() if key != 'rest'}


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
    rewrite_rulebooks(op.get_bind(), with_rest)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_rest)
