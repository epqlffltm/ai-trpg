"""outgoing notifications

Revision ID: faee8694431a
Revises: 5d8f2b0c3e4a
Create Date: 2026-10-19 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'faee8694431a'
down_revision: str | Sequence[str] | None = '5d8f2b0c3e4a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 발송함(#385). 알림 서버에 보낼 알림을 한 줄씩 적는다(app/notifications/models.py).
# 보낸 줄은 지운다. 되돌리면 아직 보내지 못한 알림이 사라진다. 개발용 DB 에서만 되돌린다

PENDING_CONDITION = "status = 'pending'"


def upgrade() -> None:
    op.create_table(
        'outgoing_notifications',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('source_key', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_error', sa.String(length=40), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'failed')", name=op.f('ck_outgoing_notifications_status_allowed')),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_outgoing_notifications_attempts_not_negative')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outgoing_notifications')),
        sa.UniqueConstraint('source_key', name=op.f('uq_outgoing_notifications_source_key')),
    )
    op.create_index(
        'ix_outgoing_notifications_due',
        'outgoing_notifications',
        ['next_attempt_at'],
        unique=False,
        postgresql_where=PENDING_CONDITION,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_outgoing_notifications_due', table_name='outgoing_notifications', postgresql_where=PENDING_CONDITION
    )
    op.drop_table('outgoing_notifications')
