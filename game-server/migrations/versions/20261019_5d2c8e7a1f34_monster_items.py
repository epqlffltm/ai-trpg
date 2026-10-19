"""monster items

Revision ID: 5d2c8e7a1f34
Revises: 897e48095259
Create Date: 2026-10-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '5d2c8e7a1f34'
down_revision: str | Sequence[str] | None = '897e48095259'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def carried_from_drops(sheet: dict) -> dict:
    """시나리오의 몬스터 시트 하나. 드롭이 소지품이 되고 장비는 없다(판 형식 34 의 올리기와 같다)."""
    moved = {key: value for key, value in sheet.items() if key != 'drops'}
    return {**moved, 'equipment': [], 'inventory': sheet.get('drops', [])}


def drops_from_carried(sheet: dict) -> dict:
    """되돌릴 때. 소지품이 드롭이 된다. 장비는 버린다."""
    moved = {key: value for key, value in sheet.items() if key not in ('equipment', 'inventory')}
    return {**moved, 'drops': sheet.get('inventory', [])}


def rewrite_monster_sheets(change) -> None:
    """모든 시나리오의 몬스터 시트를 change 로 고쳐 쓴다. 굳힌 판은 고치지 않는다. 읽을 때 올린다."""
    scenarios = sa.table('scenarios', sa.column('asset_id'), sa.column('monster_sheets', postgresql.JSONB))
    connection = op.get_bind()
    for scenario_id, sheets in connection.execute(sa.select(scenarios.c.asset_id, scenarios.c.monster_sheets)):
        if not sheets:
            continue
        rewritten = [change(sheet) for sheet in sheets]
        connection.execute(scenarios.update().where(scenarios.c.asset_id == scenario_id).values(monster_sheets=rewritten))


def upgrade() -> None:
    # 몬스터가 지닌 물건(#456). 마리마다 판의 개수에서 바뀐 줄만 적는다. 행이 없으면 판의 개수 그대로다
    op.create_table(
        'table_monster_items',
        sa.Column('monster_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_monster_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_monster_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['monster_id'],
            ['table_monsters.id'],
            name=op.f('fk_table_monster_items_monster_id_table_monsters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('monster_id', 'slot', name=op.f('pk_table_monster_items')),
    )
    # 시나리오의 드롭(drops)이 몬스터의 소지품(inventory)이 됐다. 쓰고 있던 시나리오도 옮긴다
    rewrite_monster_sheets(carried_from_drops)


def downgrade() -> None:
    rewrite_monster_sheets(drops_from_carried)
    op.drop_table('table_monster_items')
