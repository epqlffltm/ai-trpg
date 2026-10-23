"""message reports

Revision ID: c9e1f3a5b7d9
Revises: b7c9d1e3f5a7
Create Date: 2026-10-23 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c9e1f3a5b7d9'
down_revision: str | Sequence[str] | None = 'b7c9d1e3f5a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 대화 속 답의 신고와 운영자의 감사 기록(#678).
#   - message_reports: 신고와 그때 굳힌 글. 대화를 지우면(행) 함께 지워진다
#   - operator_reads, operator_actions: 덧붙이기만 한다. 고치기와 지우기를 트리거가 막는다(trpg-server 와 같다).
#     TRUNCATE 는 막지 않는다(테스트가 비울 때 쓴다). 함수와 트리거에 스키마 이름을 붙이지 않는다
# 되돌리면 기록이 모두 사라진다. 개발용 DB 에서만 되돌린다
APPEND_ONLY = ('operator_reads', 'operator_actions')


def forbid_rewrites(table: str) -> None:
    """그 표의 고치기와 지우기를 막는 함수와 트리거를 만든다."""
    op.execute(
        f"""
        CREATE FUNCTION {table}_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{table} 는 덧붙이기만 한다(%)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_rewrite
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {table}_append_only()
        """
    )


def allow_rewrites(table: str) -> None:
    """forbid_rewrites 를 되돌린다."""
    op.execute(f'DROP TRIGGER {table}_no_rewrite ON {table}')
    op.execute(f'DROP FUNCTION {table}_append_only()')


def upgrade() -> None:
    op.create_table(
        'operator_actions',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('acted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "action IN ('report_action', 'report_dismiss')", name=op.f('ck_operator_actions_action_allowed')
        ),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_actions_reason_not_blank')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_actions_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_actions')),
    )
    op.create_index('ix_operator_actions_operator', 'operator_actions', ['operator_id', 'acted_at'], unique=False)
    op.create_index('ix_operator_actions_target', 'operator_actions', ['target_id', 'acted_at'], unique=False)
    op.create_table(
        'operator_reads',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('target_kind', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_reads_reason_not_blank')),
        sa.CheckConstraint("target_kind IN ('message_report')", name=op.f('ck_operator_reads_target_kind_allowed')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_reads_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_reads')),
    )
    op.create_index('ix_operator_reads_operator', 'operator_reads', ['operator_id', 'read_at'], unique=False)
    op.create_index('ix_operator_reads_target', 'operator_reads', ['target_id', 'read_at'], unique=False)
    op.create_table(
        'message_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reporter_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('character_version', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.Text(), nullable=False),
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
    for table in APPEND_ONLY:
        forbid_rewrites(table)


def downgrade() -> None:
    for table in APPEND_ONLY:
        allow_rewrites(table)
    op.drop_index('ix_message_reports_open', table_name='message_reports', postgresql_where='handled_at IS NULL')
    op.drop_index(op.f('ix_message_reports_conversation_id'), table_name='message_reports')
    op.drop_table('message_reports')
    op.drop_index('ix_operator_reads_target', table_name='operator_reads')
    op.drop_index('ix_operator_reads_operator', table_name='operator_reads')
    op.drop_table('operator_reads')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
