"""downed by big hit

Revision ID: b4f1c8d2e6a3
Revises: 9e2b6d4a8c13
Create Date: 2026-10-19 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b4f1c8d2e6a3'
down_revision: str | Sequence[str] | None = '9e2b6d4a8c13'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 캐릭터가 큰 타격으로 쓰러졌는가(#369). 쓰러진 채 공격을 맞으면 실패가 더 쌓인다.
    # 이미 쓰러져 있는 캐릭터는 어떻게 쓰러졌는지 몰라 큰 타격이 아닌 것으로 둔다
    op.add_column(
        'table_sheets',
        sa.Column('downed_by_big_hit', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('table_sheets', 'downed_by_big_hit')
