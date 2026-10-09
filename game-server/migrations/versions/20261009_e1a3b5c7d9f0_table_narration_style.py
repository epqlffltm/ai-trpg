"""table narration style

Revision ID: e1a3b5c7d9f0
Revises: d0f2a4b6c8e9
Create Date: 2026-10-09 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1a3b5c7d9f0'
down_revision: str | Sequence[str] | None = 'd0f2a4b6c8e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
STYLES = "'none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', 'literary'"


def upgrade() -> None:
    # 칸은 자동 생성이 찾은 그대로다. 있던 테이블은 정통으로 채운다. 그 테이블의 판도 정통을 추천하는 것으로 읽힌다
    op.add_column(
        'game_tables',
        sa.Column('narration_style', sa.String(length=20), server_default=sa.text("'classic'"), nullable=False),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_game_tables_narration_style_allowed'), 'game_tables', f'narration_style IN ({STYLES})'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_game_tables_narration_style_allowed'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'narration_style')
