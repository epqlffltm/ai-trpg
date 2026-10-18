"""drop ledger drafts

Revision ID: 897e48095259
Revises: ae3a917a8ac0
Create Date: 2026-10-19 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '897e48095259'
down_revision: str | Sequence[str] | None = 'ae3a917a8ac0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 장부 초안을 걷어냈다(#371). 얻는 것은 엔진이 판으로 정한다. 쌓인 초안과 테이블의 옵션도 지운다
    op.drop_index('ix_ledger_drafts_table_status', table_name='ledger_drafts')
    op.drop_table('ledger_drafts')
    op.drop_column('game_tables', 'ledger_drafts')


def downgrade() -> None:
    # 표와 칸만 되살린다. 지운 초안은 돌아오지 않는다
    op.add_column(
        'game_tables', sa.Column('ledger_drafts', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.create_table(
        'ledger_drafts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name=op.f('ck_ledger_drafts_payload_is_object')),
        sa.CheckConstraint("kind IN ('found_item', 'quest_change')", name=op.f('ck_ledger_drafts_kind_allowed')),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'expired')", name=op.f('ck_ledger_drafts_status_allowed')
        ),
        sa.CheckConstraint('position >= 0', name=op.f('ck_ledger_drafts_position_not_negative')),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_ledger_drafts_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_ledger_drafts_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ledger_drafts')),
    )
    op.create_index('ix_ledger_drafts_table_status', 'ledger_drafts', ['table_id', 'status'], unique=False)
