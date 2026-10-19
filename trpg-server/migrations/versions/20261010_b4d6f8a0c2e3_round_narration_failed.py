"""round narration failed

Revision ID: b4d6f8a0c2e3
Revises: a3c5e7f9b1d2
Create Date: 2026-10-10 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b4d6f8a0c2e3'
down_revision: str | Sequence[str] | None = 'a3c5e7f9b1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. 있던 라운드는 실패한 적이 없는 것으로 비워 둔다.
    # 닫는 중이던 라운드는 전처럼 멈춘 지 한참 지나야 다시 맡길 수 있다
    op.add_column('table_rounds', sa.Column('narration_failed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('table_rounds', 'narration_failed_at')
