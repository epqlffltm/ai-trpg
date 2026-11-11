"""listing unlisted

Revision ID: f9a1b3c5d7e2
Revises: e8f0a2b4c6d8
Create Date: 2026-11-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f9a1b3c5d7e2'
down_revision: str | Sequence[str] | None = 'e8f0a2b4c6d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 링크 공개(#993). 있던 공개 정보는 모두 목록에 나오던 것이라 거짓이다
    op.add_column('listings', sa.Column('unlisted', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('listings', 'unlisted')
