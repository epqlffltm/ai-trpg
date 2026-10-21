"""references narration

Revision ID: c4f8a2d6e1b9
Revises: b8e3d5f1a2c7
Create Date: 2026-10-21 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c4f8a2d6e1b9'
down_revision: str | Sequence[str] | None = 'b8e3d5f1a2c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료를 서술에 섞는다(#482 2단계). 칸 셋을 더한다.
#   - worlds.references_allowed: 세계관의 제작자가 참고 자료를 허용하는가. 지금의 세계관은 허용하지 않은 것이다
#   - game_tables.references_enabled: 방장이 켰는가. 지금의 테이블은 꺼져 있다
#   - ai_invocations.reference_ids: 서술에 넣은 참고 자료의 줄들. 지금의 기록은 넣은 것이 없다


def upgrade() -> None:
    op.add_column(
        'ai_invocations', sa.Column('reference_ids', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False)
    )
    op.add_column(
        'game_tables', sa.Column('references_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'worlds', sa.Column('references_allowed', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('worlds', 'references_allowed')
    op.drop_column('game_tables', 'references_enabled')
    op.drop_column('ai_invocations', 'reference_ids')
