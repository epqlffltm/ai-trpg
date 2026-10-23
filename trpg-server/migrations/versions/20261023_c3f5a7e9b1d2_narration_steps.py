"""narration steps

Revision ID: c3f5a7e9b1d2
Revises: b7e1c9d3f5a2
Create Date: 2026-10-23 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f5a7e9b1d2'
down_revision: str | Sequence[str] | None = 'b7e1c9d3f5a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 서술의 입력·출력 단계(#387). 테이블이 고르고 라운드가 열 때 굳힌다. 있던 테이블과 라운드는 0, 0(i0.o0)이다.
# 그때 팔던 가격표가 i0.o0 하나였다. 앱의 코드를 가져오지 않는다(MAX_STEP 2)
MAX_STEP = 2
TABLES = ('game_tables', 'table_rounds')


def add_steps(table: str) -> None:
    """그 표에 입력 단계와 출력 단계를 더한다. 0 부터 MAX_STEP 까지다."""
    for column in ('input_step', 'output_step'):
        op.add_column(table, sa.Column(column, sa.SmallInteger(), server_default=sa.text('0'), nullable=False))
        op.create_check_constraint(
            op.f(f'ck_{table}_{column}_range'), table, f'{column} BETWEEN 0 AND {MAX_STEP}'
        )


def drop_steps(table: str) -> None:
    """되돌릴 때. 단계를 뺀다."""
    for column in ('input_step', 'output_step'):
        op.drop_constraint(op.f(f'ck_{table}_{column}_range'), table, type_='check')
        op.drop_column(table, column)


def upgrade() -> None:
    for table in TABLES:
        add_steps(table)


def downgrade() -> None:
    for table in TABLES:
        drop_steps(table)
