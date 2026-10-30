"""operator records

Revision ID: f6a8b0c2d4e6
Revises: e5f7a9b1c3d5
Create Date: 2026-10-31 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a8b0c2d4e6'
down_revision: str | Sequence[str] | None = 'e5f7a9b1c3d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 운영자의 감사 기록(app/operators/models.py, chat 의 #678 과 같다).
#   - operator_reads: 신고에 굳힌 세션의 글을 본 기록. operator_actions: 신고를 처리한 기록
#   - 덧붙이기만 한다. 고치기와 지우기를 트리거가 막는다. TRUNCATE 는 막지 않는다(테스트가 비울 때 쓴다).
#     함수와 트리거에 스키마 이름을 붙이지 않는다(테스트의 스키마에서도 같은 이름으로 만든다)
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
    for table in APPEND_ONLY:
        forbid_rewrites(table)


def downgrade() -> None:
    for table in APPEND_ONLY:
        allow_rewrites(table)
    op.drop_index('ix_operator_reads_target', table_name='operator_reads')
    op.drop_index('ix_operator_reads_operator', table_name='operator_reads')
    op.drop_table('operator_reads')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
