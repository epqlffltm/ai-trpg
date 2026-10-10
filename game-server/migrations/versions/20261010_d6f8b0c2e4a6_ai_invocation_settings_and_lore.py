"""ai invocation settings and lore

Revision ID: d6f8b0c2e4a6
Revises: c5e7a9b1d3f5
Create Date: 2026-10-10 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd6f8b0c2e4a6'
down_revision: str | Sequence[str] | None = 'c5e7a9b1d3f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 있던 줄의 생성 설정과 지문은 모르므로 비워 두고, 넣은 로어북은 없던 것으로 둔다.
    # CHECK 는 자동 생성이 찾지 못해 손으로 더한다
    op.add_column('ai_invocations', sa.Column('temperature', sa.Float(), nullable=True))
    op.add_column('ai_invocations', sa.Column('max_tokens', sa.Integer(), nullable=True))
    op.add_column(
        'ai_invocations', sa.Column('lore_entry_ids', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False)
    )
    op.add_column('ai_invocations', sa.Column('input_digest', sa.String(length=64), nullable=True))
    op.create_check_constraint(op.f('ck_ai_invocations_max_tokens_positive'), 'ai_invocations', 'max_tokens > 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ai_invocations_max_tokens_positive'), 'ai_invocations', type_='check')
    op.drop_column('ai_invocations', 'input_digest')
    op.drop_column('ai_invocations', 'lore_entry_ids')
    op.drop_column('ai_invocations', 'max_tokens')
    op.drop_column('ai_invocations', 'temperature')
