"""notifications

Revision ID: 3f9a1c7e5b2d
Revises:
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '3f9a1c7e5b2d'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 알림함(#385). 사람 하나에게 간 알림 하나가 한 줄이다. 규칙은 app/notifications/models.py 에 있다.
#   - (source, source_key) 가 같으면 한 줄이다. 넣는 서버가 다시 보내도 두 번 적히지 않는다
#   - 색인 셋: 내 알림함(user_id, id DESC), 읽지 않은 수(읽지 않은 줄만), 보관 기간이 지난 것 찾기(created_at)


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_key', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name=op.f('ck_notifications_payload_is_object')),
        sa.CheckConstraint(
            "kind ~ '^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$'", name=op.f('ck_notifications_kind_format')
        ),
        sa.CheckConstraint("source ~ '^[a-z][a-z0-9_-]*$'", name=op.f('ck_notifications_source_format')),
        sa.CheckConstraint('octet_length(payload::text) <= 4096', name=op.f('ck_notifications_payload_size')),
        sa.CheckConstraint(
            'read_at IS NULL OR read_at >= created_at', name=op.f('ck_notifications_read_after_created')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
        sa.UniqueConstraint('source', 'source_key', name='uq_notifications_source_key'),
    )
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'], unique=False)
    op.create_index(
        'ix_notifications_unread',
        'notifications',
        ['user_id'],
        unique=False,
        postgresql_where=sa.text('read_at IS NULL'),
    )
    op.create_index(
        'ix_notifications_user_id_id', 'notifications', ['user_id', sa.literal_column('id DESC')], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_notifications_user_id_id', table_name='notifications')
    op.drop_index('ix_notifications_unread', table_name='notifications', postgresql_where=sa.text('read_at IS NULL'))
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_table('notifications')
