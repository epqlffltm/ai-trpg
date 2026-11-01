"""table chapters

Revision ID: e2f4a6b8c0d1
Revises: c7e9a1b3d5f8
Create Date: 2026-11-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e2f4a6b8c0d1'
down_revision: str | Sequence[str] | None = 'c7e9a1b3d5f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블의 지금 장(#481). 지금 장의 id(chapter_id)와 그 장으로 넘어온 라운드(chapter_round)를 둔다.
# 이미 시작한 테이블은 비어 있어 장 없이 간다(장을 적은 판도 그 전에 시작했으면 그렇다).
# 되돌리면 두 칸을 지운다


def upgrade() -> None:
    op.add_column('game_tables', sa.Column('chapter_id', sa.String(length=40), nullable=True))
    op.add_column('game_tables', sa.Column('chapter_round', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('game_tables', 'chapter_round')
    op.drop_column('game_tables', 'chapter_id')
