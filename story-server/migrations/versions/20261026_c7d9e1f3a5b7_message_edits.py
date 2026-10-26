"""message edits

Revision ID: c7d9e1f3a5b7
Revises: b6c8d0e2f4a6
Create Date: 2026-10-26 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d9e1f3a5b7'
down_revision: str | Sequence[str] | None = 'b6c8d0e2f4a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 답 고치기(app/conversations/service.py 의 edit_message).
#   - messages.edited: 사람이 답의 글을 고쳤는가. 지금까지의 말은 고친 적이 없다(false)


def upgrade() -> None:
    op.add_column('messages', sa.Column('edited', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('messages', 'edited')
