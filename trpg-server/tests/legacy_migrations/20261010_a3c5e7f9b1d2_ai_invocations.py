"""ai invocations

Revision ID: a3c5e7f9b1d2
Revises: f2b4c6d8e0a1
Create Date: 2026-10-10 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c5e7f9b1d2'
down_revision: str | Sequence[str] | None = 'f2b4c6d8e0a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 테이블에 외래 키를 걸지 않는다. 기록은 테이블보다 오래 산다
    op.create_table(
        'ai_invocations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('purpose', sa.String(length=40), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=True),
        sa.Column('host_id', sa.Uuid(), nullable=True),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=200), nullable=False),
        sa.Column('prompt_version', sa.String(length=40), nullable=False),
        sa.Column('reasoning', sa.String(length=20), nullable=False),
        sa.Column('narration_style', sa.String(length=20), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('error', sa.String(length=40), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('finish_reason', sa.String(length=40), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.CheckConstraint("(outcome = 'ok') = (error IS NULL)", name=op.f('ck_ai_invocations_error_unless_ok')),
        sa.CheckConstraint("outcome <> 'failed' OR text IS NULL", name=op.f('ck_ai_invocations_no_text_when_failed')),
        sa.CheckConstraint("outcome IN ('ok', 'rejected', 'failed')", name=op.f('ck_ai_invocations_outcome_allowed')),
        sa.CheckConstraint(
            'input_tokens >= 0 AND output_tokens >= 0', name=op.f('ck_ai_invocations_tokens_not_negative')
        ),
        sa.CheckConstraint('latency_ms >= 0', name=op.f('ck_ai_invocations_latency_not_negative')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_invocations')),
    )
    op.create_index('ix_ai_invocations_table_id_created_at', 'ai_invocations', ['table_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_invocations_table_id_created_at', table_name='ai_invocations')
    op.drop_table('ai_invocations')
