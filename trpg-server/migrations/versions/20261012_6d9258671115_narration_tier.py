"""narration tier

Revision ID: 6d9258671115
Revises: 4ff312b39bc2
Create Date: 2026-10-12 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6d9258671115'
down_revision: str | Sequence[str] | None = '4ff312b39bc2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
TIERS = "'standard', 'premium'"
TABLES = ('game_tables', 'table_rounds')


def upgrade() -> None:
    # 있던 테이블과 라운드는 standard 다. 그때는 등급이 하나였고, 있던 청구는 모두 narration.standard 로 걸었다
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('narration_tier', sa.String(length=20), server_default=sa.text("'standard'"), nullable=False),
        )
        # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
        op.create_check_constraint(op.f(f'ck_{table}_narration_tier_allowed'), table, f'narration_tier IN ({TIERS})')


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f'ck_{table}_narration_tier_allowed'), table, type_='check')
        op.drop_column(table, 'narration_tier')
