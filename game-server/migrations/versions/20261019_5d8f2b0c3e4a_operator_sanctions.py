"""operator sanctions

Revision ID: 5d8f2b0c3e4a
Revises: 4c7e1a9b2d3f
Create Date: 2026-10-19 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5d8f2b0c3e4a'
down_revision: str | Sequence[str] | None = '4c7e1a9b2d3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 운영자의 제재(#392). docs/architecture/operators.md 의 "제재".
#   - operator_actions: 제재의 감사 기록. 덧붙이기만 한다(트리거가 UPDATE 와 DELETE 를 막는다. operator_reads 와 같다)
#   - scenario_sanctions: 제재된 판. 판 하나에 하나. 판은 테이블이 쓰므로 지워지지 않는다(RESTRICT)
#   - publishing_bans: 공개 금지. 사람마다 한 줄. 풀면 lifted_at 이 적힌다
# 되돌리면 제재와 기록이 모두 사라진다. 개발용 DB 에서만 되돌린다

ACTIONS = "'scenario_sanction', 'table_end', 'publishing_ban', 'publishing_unban'"


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
        sa.CheckConstraint(f'action IN ({ACTIONS})', name=op.f('ck_operator_actions_action_allowed')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_actions_reason_length')),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_actions_reason_not_blank')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_actions')),
    )
    op.create_index('ix_operator_actions_operator', 'operator_actions', ['operator_id', 'acted_at'])
    op.create_index('ix_operator_actions_target', 'operator_actions', ['target_id', 'acted_at'])
    op.execute(
        """
        CREATE FUNCTION operator_actions_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'operator_actions 는 덧붙이기만 한다(%)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER operator_actions_no_rewrite
        BEFORE UPDATE OR DELETE ON operator_actions
        FOR EACH ROW EXECUTE FUNCTION operator_actions_append_only()
        """
    )

    op.create_table(
        'scenario_sanctions',
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('sanctioned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['scenario_versions.id'],
            name=op.f('fk_scenario_sanctions_version_id_scenario_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('version_id', name=op.f('pk_scenario_sanctions')),
    )
    op.create_index('ix_scenario_sanctions_owner', 'scenario_sanctions', ['owner_id', 'sanctioned_at'])

    op.create_table(
        'publishing_bans',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('banned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('banned_by', sa.Uuid(), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('lifted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lifted_by', sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_publishing_bans')),
    )


def downgrade() -> None:
    op.drop_table('publishing_bans')
    op.drop_index('ix_scenario_sanctions_owner', table_name='scenario_sanctions')
    op.drop_table('scenario_sanctions')
    op.execute('DROP TRIGGER operator_actions_no_rewrite ON operator_actions')
    op.execute('DROP FUNCTION operator_actions_append_only()')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
