"""summary claims

Revision ID: 966f93ce25d6
Revises: b8d0f2a4c6e8
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '966f93ce25d6'
down_revision: str | Sequence[str] | None = 'b8d0f2a4c6e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 굴리는 요약을 쓰는 중인 시각(#674). 서버가 여럿이어도 한 대화에 한 번에 하나만 쓴다(app/memory/repository.py).
# 있던 줄은 비어 있다(쓰는 중이 아니다). 되돌리면 서버 사이의 막기만 없어진다


def upgrade() -> None:
    op.add_column('conversations', sa.Column('summarizing_since', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'summarizing_since')
