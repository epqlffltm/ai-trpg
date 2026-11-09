"""world achievements

Revision ID: e7a9c1d3f5b7
Revises: d9f1b3c5e7a9
Create Date: 2026-11-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e7a9c1d3f5b7'
down_revision: str | Sequence[str] | None = 'd9f1b3c5e7a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세계관의 업적(판의 형식 9, docs/architecture/achievements.md 의 "story"). 있던 초안은 업적이 없다(빈 목록).
# 세계관의 장을 더한 리비전(d9f1b3c5e7a9)에서 갈라진다. 다른 마이그레이션의 차례에 기대지 않는다(upgrade heads)


def upgrade() -> None:
    op.add_column(
        'worlds',
        sa.Column('achievements', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('worlds', 'achievements')
