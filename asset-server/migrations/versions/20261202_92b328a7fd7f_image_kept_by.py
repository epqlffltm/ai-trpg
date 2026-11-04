"""image kept by

Revision ID: 92b328a7fd7f
Revises: d2f63000fa2d
Create Date: 2026-12-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '92b328a7fd7f'
down_revision: str | Sequence[str] | None = 'd2f63000fa2d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 그림을 맡긴 서버(#983, app/images/models.py 의 kept_by). 그 서버는 서명만으로 그 바이트를 받는다.
# 이미 있는 그림은 비워 둔다(사용자가 올렸거나, 이 칸이 생기기 전에 chat·story 가 맡겼다. 둘 다 kept 로 받지 않는다)


def upgrade() -> None:
    op.add_column('images', sa.Column('kept_by', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('images', 'kept_by')
