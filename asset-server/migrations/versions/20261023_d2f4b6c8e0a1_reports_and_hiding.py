"""reports and hiding

Revision ID: d2f4b6c8e0a1
Revises: c1e3a5b7d9f0
Create Date: 2026-10-23 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f4b6c8e0a1'
down_revision: str | Sequence[str] | None = 'c1e3a5b7d9f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 신고와 운영자의 숨김(#678).
#   - character_reports: 공개 캐릭터의 신고. 같은 사람이 같은 캐릭터를 두 번 신고하지 못한다
#   - operator_actions: 운영자가 한 조치의 감사 기록. 덧붙이기만 한다. 고치기와 지우기를 트리거가 막는다
#     (trpg-server 의 operator_actions 와 같다). TRUNCATE 는 막지 않는다(테스트가 비울 때 쓴다).
#     함수와 트리거에 스키마 이름을 붙이지 않는다. 연결의 search_path 가 asset 이나 asset_test 를 가리킨다
#   - characters.hidden_at: 운영자가 숨긴 시각. 있던 캐릭터는 숨기지 않은 것이다
# 되돌리면 기록이 모두 사라진다. 개발용 DB 에서만 되돌린다


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
            "action IN ('character_hide', 'character_unhide', 'reports_dismiss')",
            name=op.f('ck_operator_actions_action_allowed'),
        ),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_actions_reason_not_blank')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_actions_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_actions')),
    )
    op.create_index('ix_operator_actions_operator', 'operator_actions', ['operator_id', 'acted_at'], unique=False)
    op.create_index('ix_operator_actions_target', 'operator_actions', ['target_id', 'acted_at'], unique=False)
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
        'character_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('reporter_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handled_by', sa.Uuid(), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('actioned', 'dismissed')", name=op.f('ck_character_reports_outcome_allowed')
        ),
        sa.CheckConstraint(
            "reason IN ('spam', 'abuse', 'sexual', 'minor', 'illegal', 'other')",
            name=op.f('ck_character_reports_reason_allowed'),
        ),
        sa.CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=op.f('ck_character_reports_handled_together'),
        ),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_reports_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_character_reports')),
        sa.UniqueConstraint('reporter_id', 'character_id', name='uq_character_reports_reporter_character'),
    )
    op.create_index(
        'ix_character_reports_open',
        'character_reports',
        ['character_id'],
        unique=False,
        postgresql_where='handled_at IS NULL',
    )
    op.add_column('characters', sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('characters', 'hidden_at')
    op.drop_index('ix_character_reports_open', table_name='character_reports', postgresql_where='handled_at IS NULL')
    op.drop_table('character_reports')
    op.execute('DROP TRIGGER operator_actions_no_rewrite ON operator_actions')
    op.execute('DROP FUNCTION operator_actions_append_only()')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
