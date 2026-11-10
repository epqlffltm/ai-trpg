"""chapter branches

Revision ID: e3a5c7d9f1b2
Revises: d1f7b3a5c9e8
Create Date: 2026-12-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e3a5c7d9f1b2'
down_revision: str | Sequence[str] | None = 'd1f7b3a5c9e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장의 갈림길(#289).
#   - game_tables.chapter_path: 지나온 장의 id 들(첫 장부터 지금 장까지). 있던 테이블은 빈 목록이고,
#     그때는 판의 첫 장부터 지금 장까지로 본다(갈림길이 생기기 전에는 장이 한 줄이었다)
# 되돌리면 칸을 지운다. 갈림길이 있는 판의 테이블은 한 줄로 본 지나온 장을 쓰게 된다


def upgrade() -> None:
    op.add_column(
        'game_tables',
        sa.Column(
            'chapter_path',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f('ck_game_tables_chapter_path_is_array'), 'game_tables', "jsonb_typeof(chapter_path) = 'array'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_game_tables_chapter_path_is_array'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'chapter_path')
