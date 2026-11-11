"""expired quests

Revision ID: c7d2e9a4f1b6
Revises: b4f1c8d2e6a3
Create Date: 2026-10-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c7d2e9a4f1b6'
down_revision: str | Sequence[str] | None = 'b4f1c8d2e6a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 라운드가 닫힐 때 기한을 넘겨 실패한 퀘스트들(#268). 서술이 그 라운드에 때를 놓친 것을 그린다.
    # 이미 닫힌 라운드는 빈 목록이다. 그때는 서술에 알리지 않았다
    op.add_column(
        'table_rounds',
        sa.Column(
            'expired_quests', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column('table_rounds', 'expired_quests')
