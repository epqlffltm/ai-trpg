"""ledger drafts

Revision ID: d0ae2b47aaa9
Revises: 4023c8b48079
Create Date: 2026-10-14 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd0ae2b47aaa9'
down_revision: str | Sequence[str] | None = '4023c8b48079'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 있던 테이블은 장부 초안을 쓰지 않는다(false). 방장이 켠다
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
    op.add_column(
        'game_tables', sa.Column('ledger_drafts', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('game_tables', 'ledger_drafts')
    op.drop_index('ix_ledger_drafts_table_status', table_name='ledger_drafts')
    op.drop_table('ledger_drafts')
