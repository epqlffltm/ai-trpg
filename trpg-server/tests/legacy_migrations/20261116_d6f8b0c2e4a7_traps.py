"""traps

Revision ID: d6f8b0c2e4a7
Revises: c5e7a9b1d3f6
Create Date: 2026-11-16 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd6f8b0c2e4a7'
down_revision: str | Sequence[str] | None = 'c5e7a9b1d3f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 덫(#806). 테이블의 장소에 놓인 덫(table_traps)을 둔다. 부상이 덫의 효과로도 생긴다(source 'trap').
# 아이템 규칙의 덫(items[].trap)은 시나리오의 문서 칸(JSONB)과 굳힌 판에 있다. 비워도 되는 칸이라 고치지 않는다.
# 되돌리면 덫과 덫으로 생긴 부상을 지우고, 덫을 놓는 선언의 행동을 비우고, 시나리오의 아이템 규칙에서 덫을 뺀다.
# 굳힌 판은 고치지 않는다. 앱의 코드를 가져오지 않는다

SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill', 'attack', 'trap')"
OLD_SOURCES = "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill', 'attack')"


def without_traps(rules: list[dict] | None) -> list[dict]:
    """되돌릴 때. 아이템 규칙들에서 덫을 뺀다."""
    return [{key: value for key, value in rule.items() if key != 'trap'} for rule in rules or []]


def rewrite_item_rules(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 아이템 규칙에서 덫을 뺀다. 바뀐 것만 적는다."""
    for scenario_id, items in connection.execute(sa.text('SELECT asset_id, items FROM scenarios')).all():
        changed = without_traps(items)
        if changed != (items or []):
            connection.execute(
                sa.text('UPDATE scenarios SET items = CAST(:items AS JSONB) WHERE asset_id = :id'),
                {'items': json.dumps(changed), 'id': scenario_id},
            )


def upgrade() -> None:
    op.create_table(
        'table_traps',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('set_by', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_reason', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_traps_round_number_positive')),
        sa.CheckConstraint("ended_reason IN ('sprung', 'disarmed')", name=op.f('ck_table_traps_ended_reason_allowed')),
        sa.CheckConstraint('(ended_at IS NULL) = (ended_reason IS NULL)', name=op.f('ck_table_traps_end_has_reason')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_traps_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_traps')),
    )
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', SOURCES)


def downgrade() -> None:
    op.execute("UPDATE round_declarations SET action = NULL WHERE action->>'kind' = 'set_trap'")
    # 덫으로 생긴 부상은 되돌린 모양에 들어갈 자리가 없다. 지운다
    op.execute("DELETE FROM table_injuries WHERE source = 'trap'")
    op.drop_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', type_='check')
    op.create_check_constraint(op.f('ck_table_injuries_source_allowed'), 'table_injuries', OLD_SOURCES)
    op.drop_table('table_traps')
    rewrite_item_rules(op.get_bind())
