"""ai call input chars

Revision ID: 5b2e9c41d7a3
Revises: 0765ce020cf6
Create Date: 2026-10-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5b2e9c41d7a3'
down_revision: str | Sequence[str] | None = '0765ce020cf6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# AI 호출의 기록에 보낸 메시지의 글자 수를 더한다(app/rounds/budget.py, #332).
# 서술의 입력 예산을 글자 수로 어림하고, 이 칸과 입력 토큰 수를 견주어 글자당 토큰 수를 고친다.
# 비워 둘 수 있다. 이 칸이 생기기 전의 줄은 비어 있다.
# 조건의 글자는 모델(app/ai/models.py)과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
INPUT_CHARS = 'input_chars >= 0'


def upgrade() -> None:
    op.add_column('ai_invocations', sa.Column('input_chars', sa.Integer(), nullable=True))
    op.create_check_constraint(op.f('ck_ai_invocations_input_chars_not_negative'), 'ai_invocations', INPUT_CHARS)


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ai_invocations_input_chars_not_negative'), 'ai_invocations', type_='check')
    op.drop_column('ai_invocations', 'input_chars')
