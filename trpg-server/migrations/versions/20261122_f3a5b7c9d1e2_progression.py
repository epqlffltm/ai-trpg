"""progression

Revision ID: f3a5b7c9d1e2
Revises: e2f4a6b8c0d1
Create Date: 2026-11-22 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a5b7c9d1e2'
down_revision: str | Sequence[str] | None = 'e2f4a6b8c0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 성장(#286). 룰북의 규칙에 성장(progression)을 더하고, 테이블의 시트에 경험치(xp)와
# 아직 놓지 않은 능력치 점수(points)를 둔다.
# 이미 있는 룰북은 성장이 없는 규칙(null)이다. 하던 대로 돈다. 이미 있는 시트는 경험치와 점수가 0 이다.
# 굳힌 판은 고치지 않는다. 읽을 때 올린다(app/assets/scenarios/upgrades.py 의 upgrade_from_67, 같은 값).
# 시나리오의 퀘스트의 경험치의 보상(reward_xp)은 비워도 되는 칸이라 올릴 때 고치지 않는다.
# 되돌리면 시트의 두 칸을 지우고, 룰북의 규칙에서 성장을, 시나리오의 퀘스트에서 경험치의 보상을 뺀다
# (그때의 모양은 모르는 칸을 받지 않는다). 앱의 코드를 가져오지 않는다


def with_progression(rules: dict) -> dict:
    """룰북의 규칙. 성장이 없으면 성장이 없는 규칙(null)으로 채운다. 이미 있으면 그대로다(두 번 돌려도 같다)."""
    return rules if 'progression' in rules else {**rules, 'progression': None}


def without_progression(rules: dict) -> dict:
    """되돌릴 때. 룰북의 규칙에서 성장을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'progression'}


def quest_without_xp(quest: dict) -> dict:
    """되돌릴 때. 퀘스트 규칙 하나에서 경험치의 보상을 뺀다."""
    return {key: value for key, value in quest.items() if key != 'reward_xp'}


def rewrite_rulebooks(connection: sa.Connection, step) -> None:
    """모든 룰북의 규칙을 step 으로 고쳐 쓴다. 바뀐 것만 적는다."""
    for rulebook_id, rules in connection.execute(sa.text('SELECT asset_id, rules FROM rulebooks')).all():
        changed = step(rules)
        if changed != rules:
            connection.execute(
                sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB) WHERE asset_id = :id'),
                {'rules': json.dumps(changed), 'id': rulebook_id},
            )


def rewrite_quests(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 퀘스트 규칙에서 경험치의 보상을 뺀다. 바뀐 것만 적는다."""
    for scenario_id, quests in connection.execute(sa.text('SELECT asset_id, quests FROM scenarios')).all():
        changed = [quest_without_xp(quest) for quest in quests or []]
        if changed != (quests or []):
            connection.execute(
                sa.text('UPDATE scenarios SET quests = CAST(:quests AS JSONB) WHERE asset_id = :id'),
                {'quests': json.dumps(changed), 'id': scenario_id},
            )


def upgrade() -> None:
    rewrite_rulebooks(op.get_bind(), with_progression)
    op.add_column('table_sheets', sa.Column('xp', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('table_sheets', sa.Column('points', sa.SmallInteger(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint(op.f('ck_table_sheets_xp_not_negative'), 'table_sheets', 'xp >= 0')
    op.create_check_constraint(op.f('ck_table_sheets_points_not_negative'), 'table_sheets', 'points >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_sheets_points_not_negative'), 'table_sheets', type_='check')
    op.drop_constraint(op.f('ck_table_sheets_xp_not_negative'), 'table_sheets', type_='check')
    op.drop_column('table_sheets', 'points')
    op.drop_column('table_sheets', 'xp')
    rewrite_quests(op.get_bind())
    rewrite_rulebooks(op.get_bind(), without_progression)
