"""npc items

Revision ID: 6e1a9c4d2b75
Revises: 3a9d7c5e1b82
Create Date: 2026-10-19 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6e1a9c4d2b75'
down_revision: str | Sequence[str] | None = '3a9d7c5e1b82'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NPC 가 지닌 물건(#457). 몬스터처럼 판의 개수에서 바뀐 줄만 적는다. 행이 없으면 판의 개수 그대로다
    op.create_table(
        'table_npc_items',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_npc_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_npc_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id', 'entry_id'],
            ['table_npcs.table_id', 'table_npcs.entry_id'],
            name=op.f('fk_table_npc_items_table_id_table_npcs'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', 'slot', name=op.f('pk_table_npc_items')),
    )
    # 처음 쓰러진 라운드. 드롭은 그때 한 번만 굴린다. 이미 쓰러져 있던 인물은 비워 둔다.
    # 이 칸이 생기기 전에는 NPC 가 아무것도 지니지 않아 드롭이 없었으므로 다시 굴려도 나올 것이 없다
    op.add_column('table_npcs', sa.Column('fell_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_npcs_fell_round_positive'), 'table_npcs', 'fell_round IS NULL OR fell_round >= 1'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_npcs_fell_round_positive'), 'table_npcs', type_='check')
    op.drop_column('table_npcs', 'fell_round')
    op.drop_table('table_npc_items')
