"""rule narration

Revision ID: b7e1c9d3f5a2
Revises: a4d8e2c6f1b3
Create Date: 2026-10-23 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e1c9d3f5a2'
down_revision: str | Sequence[str] | None = 'a4d8e2c6f1b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 룰북의 규칙에 서술 지침(narration, #616)의 칸을 더한다. 판은 읽을 때 올린다
# (app/assets/scenarios/upgrades.py 의 upgrade_from_44). 옛 룰북은 지침이 없는 것(null)으로 둔다.
# SRD5 템플릿의 지침(판타지)을 채우지 않는다. 그때까지 SRD5 의 규칙은 장르를 가리지 않고 쓰였다.
# 앱의 코드를 가져오지 않는다


def with_narration(rules: dict) -> dict:
    """서술 지침의 칸이 없는 규칙에 빈 지침(null)을 더한다. 이미 있으면 그대로 둔다."""
    if 'narration' in rules:
        return rules
    return {**rules, 'narration': None}


def without_narration(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 서술 지침을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'narration'}


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
    rewrite_rulebooks(op.get_bind(), with_narration)


def downgrade() -> None:
    rewrite_rulebooks(op.get_bind(), without_narration)
