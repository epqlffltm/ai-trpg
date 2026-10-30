"""trap finding

Revision ID: e8a0c2d4f6b9
Revises: d6f8b0c2e4a7
Create Date: 2026-11-17 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e8a0c2d4f6b9'
down_revision: str | Sequence[str] | None = 'd6f8b0c2e4a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 덫 찾기와 해제(#806 ①-b). 테이블의 덫에 찾아낸 시각(found_at)을 둔다. 이미 놓인 덫은 아무도 찾지 못한 것이다.
# 아이템 규칙의 덫의 찾기 판정(items[].trap.find)은 비워도 되는 칸이라 올릴 때 고치지 않는다. 굳힌 판도 고치지 않는다.
# 되돌리면 찾은 시각을 지우고, 해제하는 선언의 행동을 비우고, 시나리오의 덫에서 찾기 판정을 뺀다.
# 해제로 끝난 덫(ended_reason 'disarmed')은 그 전 모양에도 있는 값이라 그대로 둔다. 앱의 코드를 가져오지 않는다


def without_find(rules: list[dict] | None) -> list[dict]:
    """되돌릴 때. 아이템 규칙들의 덫에서 찾기 판정을 뺀다. 덫이 없는 규칙은 그대로다."""
    return [
        {**rule, 'trap': {key: value for key, value in rule['trap'].items() if key != 'find'}}
        if isinstance(rule.get('trap'), dict)
        else rule
        for rule in rules or []
    ]


def rewrite_item_rules(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 아이템 규칙의 덫에서 찾기 판정을 뺀다. 바뀐 것만 적는다."""
    for scenario_id, items in connection.execute(sa.text('SELECT asset_id, items FROM scenarios')).all():
        changed = without_find(items)
        if changed != (items or []):
            connection.execute(
                sa.text('UPDATE scenarios SET items = CAST(:items AS JSONB) WHERE asset_id = :id'),
                {'items': json.dumps(changed), 'id': scenario_id},
            )


def upgrade() -> None:
    op.add_column('table_traps', sa.Column('found_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("UPDATE round_declarations SET action = NULL WHERE action->>'kind' = 'disarm'")
    op.drop_column('table_traps', 'found_at')
    rewrite_item_rules(op.get_bind())
