"""edited

Revision ID: b5c7d9e1f3a4
Revises: a4b6c8d0e2f3
Create Date: 2026-10-22 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b5c7d9e1f3a4'
down_revision: str | Sequence[str] | None = 'a4b6c8d0e2f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 상대의 말 고치기. 사람이 고친 캐릭터의 말에 표시를 단다. 있던 말은 고치지 않은 것이다


def upgrade() -> None:
    op.add_column('messages', sa.Column('edited', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('messages', 'edited')
