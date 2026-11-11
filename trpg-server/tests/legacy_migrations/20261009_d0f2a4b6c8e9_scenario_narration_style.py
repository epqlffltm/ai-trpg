"""scenario narration style

Revision ID: d0f2a4b6c8e9
Revises: c9e1f3a5b7d8
Create Date: 2026-10-09 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd0f2a4b6c8e9'
down_revision: str | Sequence[str] | None = 'c9e1f3a5b7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
STYLES = "'none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', 'literary'"


def upgrade() -> None:
    # 칸은 자동 생성이 찾은 그대로다. 있던 시나리오는 정통을 추천하는 것으로 채운다.
    # 제작자가 고르지 않았을 때의 기본과 같다
    op.add_column(
        'scenarios',
        sa.Column('narration_style', sa.String(length=20), server_default=sa.text("'classic'"), nullable=False),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_scenarios_narration_style_allowed'), 'scenarios', f'narration_style IN ({STYLES})'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_narration_style_allowed'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'narration_style')
