"""narration failures

Revision ID: 3f7a9c1e5b2d
Revises: 8c4d2a6e1f3b
Create Date: 2026-10-18 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3f7a9c1e5b2d'
down_revision: str | Sequence[str] | None = '8c4d2a6e1f3b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 라운드에 서술이 실패로 끝난 횟수를 더한다(#332). 정해 둔 횟수에 닿으면 서술을 그만두고 값을 받지 않는다.
# 이 칸이 생기기 전의 라운드는 0 이다.
# 조건의 글자는 모델(app/rounds/models.py)과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
NOT_NEGATIVE = 'narration_failures >= 0'


def upgrade() -> None:
    op.add_column(
        'table_rounds',
        sa.Column('narration_failures', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    )
    op.create_check_constraint(op.f('ck_table_rounds_narration_failures_not_negative'), 'table_rounds', NOT_NEGATIVE)


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_rounds_narration_failures_not_negative'), 'table_rounds', type_='check')
    op.drop_column('table_rounds', 'narration_failures')
