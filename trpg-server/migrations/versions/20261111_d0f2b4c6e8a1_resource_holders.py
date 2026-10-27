"""resource holders

Revision ID: d0f2b4c6e8a1
Revises: c9e1a3b5d7f0
Create Date: 2026-11-11 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd0f2b4c6e8a1'
down_revision: str | Sequence[str] | None = 'c9e1a3b5d7f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NPC 와 몬스터도 수치를 가진다(#804). 수치에 가진 쪽(holders)을 더한다. 비우면 캐릭터만이라 이미 있는 룰북과
# 굳힌 판은 그대로 읽힌다(고치지 않는다). NPC 와 몬스터의 상태에 지금 값(resources)을 둔다. 적힌 것이 없으면 시작 값이다.
# 되돌리면 그 칸들을 지우고 룰북의 수치에서 holders 를 뺀다. NPC 나 몬스터만 가지던 수치는 캐릭터의 수치로 남는다.
# 앱의 코드를 가져오지 않는다

TABLES = ('table_npcs', 'table_monsters')


def without_holders(rules: dict) -> dict:
    """되돌릴 때. 수치마다 가진 쪽을 뺀다. 수치가 없는 규칙은 그대로다."""
    if not rules.get('resources'):
        return rules
    resources = [{key: value for key, value in resource.items() if key != 'holders'} for resource in rules['resources']]
    return {**rules, 'resources': resources}


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
    for table in TABLES:
        op.add_column(
            table, sa.Column('resources', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False)
        )
        op.create_check_constraint(op.f(f'ck_{table}_resources_is_object'), table, "jsonb_typeof(resources) = 'object'")


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f'ck_{table}_resources_is_object'), table, type_='check')
        op.drop_column(table, 'resources')
    rewrite_rulebooks(op.get_bind(), without_holders)
