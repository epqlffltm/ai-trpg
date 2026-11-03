"""message shortcut

Revision ID: 3b2bac77b5aa
Revises: c2919b23cd94
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3b2bac77b5aa'
down_revision: str | Sequence[str] | None = 'c2919b23cd94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 사람의 말이 부른 단축어의 본문(#981, app/conversations/models.py 의 Message.shortcut_body).
# 지금까지의 말은 비어 있다. 되돌리면 적어 둔 본문이 사라진다(그 말을 다시 쓰면 단축어 없이 쓴다)


def upgrade() -> None:
    op.add_column('messages', sa.Column('shortcut_body', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'shortcut_body')
