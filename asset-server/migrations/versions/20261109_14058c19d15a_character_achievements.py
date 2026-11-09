"""character achievements

Revision ID: 14058c19d15a
Revises: 3697d9b8eb2a
Create Date: 2026-11-09 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '14058c19d15a'
down_revision: str | Sequence[str] | None = '3697d9b8eb2a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 업적(판의 형식 11, docs/architecture/achievements.md 의 "chat"). 있던 초안은 업적이 없다(빈 목록).
# 캐릭터에 단축어를 더한 리비전(3697d9b8eb2a)에서 갈라진다. 다른 마이그레이션의 차례에 기대지 않는다(upgrade heads)


def upgrade() -> None:
    op.add_column(
        'characters',
        sa.Column('achievements', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('characters', 'achievements')
