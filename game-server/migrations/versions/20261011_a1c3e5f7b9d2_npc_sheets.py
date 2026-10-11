"""npc sheets

Revision ID: a1c3e5f7b9d2
Revises: f9b1d3e5a7c9
Create Date: 2026-10-11 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1c3e5f7b9d2'
down_revision: str | Sequence[str] | None = 'f9b1d3e5a7c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 시나리오는 NPC 시트가 없는 것으로 둔다. 인물 항목이 있으면 다음에 게시할 때 기본 NPC 시트가 있어야 한다.
    # 이미 굳힌 판은 읽을 때 올린다(형식 13). 진행 중인 테이블에는 NPC 상태를 채우지 않는다
    op.add_column(
        'scenarios',
        sa.Column(
            'npc_sheets', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.add_column('scenarios', sa.Column('default_npc_sheet', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # CHECK 조건은 자동 생성이 찾지 못한다. 모델과 같은 것을 직접 적는다
    op.create_check_constraint(
        op.f('ck_scenarios_npc_sheets_count'), 'scenarios', 'jsonb_array_length(npc_sheets) <= 100'
    )
    op.create_table(
        'table_npcs',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('max_hp', sa.SmallInteger(), nullable=False),
        sa.Column('hp', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'alive'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('max_hp >= 1', name=op.f('ck_table_npcs_max_hp_positive')),
        sa.CheckConstraint('hp BETWEEN 0 AND max_hp', name=op.f('ck_table_npcs_hp_range')),
        sa.CheckConstraint("status IN ('alive', 'downed', 'dead')", name=op.f('ck_table_npcs_status_allowed')),
        sa.CheckConstraint("(status = 'alive') = (hp > 0)", name=op.f('ck_table_npcs_alive_when_hp')),
        sa.CheckConstraint("jsonb_typeof(abilities) = 'object'", name=op.f('ck_table_npcs_abilities_is_object')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_npcs_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_npcs')),
    )


def downgrade() -> None:
    op.drop_table('table_npcs')
    op.drop_constraint(op.f('ck_scenarios_npc_sheets_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'default_npc_sheet')
    op.drop_column('scenarios', 'npc_sheets')
