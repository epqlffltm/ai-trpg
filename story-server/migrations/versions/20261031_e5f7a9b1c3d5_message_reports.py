"""message reports

Revision ID: e5f7a9b1c3d5
Revises: d4e6f8a0b2c4
Create Date: 2026-10-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e5f7a9b1c3d5'
down_revision: str | Sequence[str] | None = 'd4e6f8a0b2c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세션 속 답의 신고(app/reports/models.py, chat 의 #678 과 같다). 신고와 그때 굳힌 글이다.
# 세션의 행이 지워지면(탈퇴) 함께 지워진다. 운영자의 감사 기록은 운영자 API 와 함께 더한다


def upgrade() -> None:
    op.create_table(
        'message_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reporter_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('world_version', sa.Integer(), nullable=False),
        sa.Column('world_name', sa.Text(), nullable=False),
        sa.Column('model_slug', sa.String(length=100), nullable=True),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handled_by', sa.Uuid(), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('actioned', 'dismissed')", name=op.f('ck_message_reports_outcome_allowed')
        ),
        sa.CheckConstraint(
            "reason IN ('spam', 'abuse', 'sexual', 'minor', 'illegal', 'other')",
            name=op.f('ck_message_reports_reason_allowed'),
        ),
        sa.CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=op.f('ck_message_reports_handled_together'),
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_message_reports_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_message_reports_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_message_reports')),
        sa.UniqueConstraint('reporter_id', 'message_id', name='uq_message_reports_reporter_message'),
    )
    op.create_index(op.f('ix_message_reports_conversation_id'), 'message_reports', ['conversation_id'], unique=False)
    op.create_index(
        'ix_message_reports_open',
        'message_reports',
        ['created_at'],
        unique=False,
        postgresql_where='handled_at IS NULL',
    )


def downgrade() -> None:
    op.drop_index('ix_message_reports_open', table_name='message_reports', postgresql_where='handled_at IS NULL')
    op.drop_index(op.f('ix_message_reports_conversation_id'), table_name='message_reports')
    op.drop_table('message_reports')
