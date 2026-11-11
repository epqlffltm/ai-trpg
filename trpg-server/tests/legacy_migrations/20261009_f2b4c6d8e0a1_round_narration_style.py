"""round narration style

Revision ID: f2b4c6d8e0a1
Revises: e1a3b5c7d9f0
Create Date: 2026-10-09 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2b4c6d8e0a1'
down_revision: str | Sequence[str] | None = 'e1a3b5c7d9f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
STYLES = "'none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', 'literary'"


def upgrade() -> None:
    # 칸은 자동 생성이 찾은 그대로다. 있던 라운드는 비워 둔다.
    # 닫힌 라운드는 이 칸을 읽지 않는다. 닫는 중이던 라운드는 지금 테이블의 문체로 서술한다(service.frozen_style)
    op.add_column('table_rounds', sa.Column('narration_style', sa.String(length=20), nullable=True))
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_table_rounds_narration_style_allowed'), 'table_rounds', f'narration_style IN ({STYLES})'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_rounds_narration_style_allowed'), 'table_rounds', type_='check')
    op.drop_column('table_rounds', 'narration_style')
