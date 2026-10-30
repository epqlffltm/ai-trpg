"""conversation deleted at

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b3
Create Date: 2026-10-30 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e6f8a0b2c4'
down_revision: str | Sequence[str] | None = 'c3d5e7f9a1b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세션 지우기(chat 과 같다). 지운 시각만 적고 행은 남긴다. 행을 지우는 것은 탈퇴뿐이다


def upgrade() -> None:
    op.add_column('conversations', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'deleted_at')
