"""equipment slots

Revision ID: e5b7d9f1a3c6
Revises: d4a6c8e0f2b5
Create Date: 2026-10-24 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e5b7d9f1a3c6'
down_revision: str | Sequence[str] | None = 'd4a6c8e0f2b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장비의 칸(#276). 룰북의 규칙에 칸(equipment_slots)을 더하고, 캐릭터가 착용한 것(table_worn)을 둔다.
# 옛 룰북은 칸이 없는 것([])으로 둔다. SRD5 템플릿의 칸을 채우지 않는다(서술 지침과 같다). 판은 읽을 때 올린다
# (app/assets/scenarios/upgrades.py 의 upgrade_from_46). 앱의 코드를 가져오지 않는다


def with_slots(rules: dict) -> dict:
    """칸이 없는 규칙에 빈 칸의 목록을 더한다. 이미 있으면 그대로 둔다."""
    if 'equipment_slots' in rules:
        return rules
    return {**rules, 'equipment_slots': []}


def without_slots(rules: dict) -> dict:
    """되돌릴 때. 규칙에서 칸을 뺀다."""
    return {key: value for key, value in rules.items() if key != 'equipment_slots'}


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
    rewrite_rulebooks(op.get_bind(), with_slots)
    op.create_table(
        'table_worn',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('slots', postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cardinality(slots) >= 1', name=op.f('ck_table_worn_slots_not_empty')),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_worn_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_worn_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_worn')),
    )
    op.create_index(op.f('ix_table_worn_table_id'), 'table_worn', ['table_id'])
    op.create_index(op.f('ix_table_worn_sheet_id'), 'table_worn', ['sheet_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_table_worn_sheet_id'), table_name='table_worn')
    op.drop_index(op.f('ix_table_worn_table_id'), table_name='table_worn')
    op.drop_table('table_worn')
    rewrite_rulebooks(op.get_bind(), without_slots)
