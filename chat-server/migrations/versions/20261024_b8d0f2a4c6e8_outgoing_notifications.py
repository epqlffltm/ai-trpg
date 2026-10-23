"""outgoing notifications

Revision ID: b8d0f2a4c6e8
Revises: c9e1f3a5b7d9
Create Date: 2026-10-24 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8d0f2a4c6e8'
down_revision: str | Sequence[str] | None = 'c9e1f3a5b7d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 알림 서버에 보낼 알림의 발송함(#678). 칸과 규칙은 server_core/notifications/models.py 에 있다.
# trpg-server 의 outgoing_notifications 와 같은 모양이다. 보낸 줄은 지우고, 받지 않은 줄(failed)만 남는다.
# 되돌리면 아직 보내지 못한 알림이 사라진다

# 보낼 차례를 찾는 색인의 조건(기다리는 것만 담는다). 모델의 PENDING_CONDITION 과 같은 글자다
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
