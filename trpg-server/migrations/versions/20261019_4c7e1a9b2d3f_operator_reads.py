"""operator reads

Revision ID: 4c7e1a9b2d3f
Revises: 2e6b8d4f9a3c
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4c7e1a9b2d3f'
down_revision: str | Sequence[str] | None = '2e6b8d4f9a3c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 운영자가 남의 것을 본 기록(operator_reads, #391). docs/architecture/operators.md 의 "감사 기록".
#   - 덧붙이기만 한다. 고치기와 지우기를 트리거가 막는다. 결제 서버의 원장과 같은 방식이다.
#     TRUNCATE 는 막지 않는다(행마다 도는 트리거가 걸리지 않는다). 테스트가 비울 때 쓴다(tests/cleaning.py).
#     그 권한은 마이그레이션을 돌리는 계정에만 있어야 한다. 앱의 계정이 같은 계정이면 이 막음은 실수를 막는 데까지다.
#   - 함수와 트리거에 스키마 이름을 붙이지 않는다. 연결의 search_path 가 game 이나 game_test 를 가리킨다.
# 되돌리면 기록이 모두 사라진다. 개발용 DB 에서만 되돌린다

KINDS = "'table', 'table_events', 'table_messages', 'table_whispers', 'scenario', 'scenario_version'"


def upgrade() -> None:
    op.create_table(
        'operator_reads',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('target_kind', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('target_number', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint(f'target_kind IN ({KINDS})', name=op.f('ck_operator_reads_target_kind_allowed')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_reads_reason_length')),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_reads_reason_not_blank')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_reads')),
    )
    op.create_index('ix_operator_reads_operator', 'operator_reads', ['operator_id', 'read_at'])
    op.create_index('ix_operator_reads_target', 'operator_reads', ['target_id', 'read_at'])
    op.execute(
        """
        CREATE FUNCTION operator_reads_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'operator_reads 는 덧붙이기만 한다(%)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER operator_reads_no_rewrite
        BEFORE UPDATE OR DELETE ON operator_reads
        FOR EACH ROW EXECUTE FUNCTION operator_reads_append_only()
        """
    )


def downgrade() -> None:
    op.execute('DROP TRIGGER operator_reads_no_rewrite ON operator_reads')
    op.execute('DROP FUNCTION operator_reads_append_only()')
    op.drop_index('ix_operator_reads_target', table_name='operator_reads')
    op.drop_index('ix_operator_reads_operator', table_name='operator_reads')
    op.drop_table('operator_reads')
