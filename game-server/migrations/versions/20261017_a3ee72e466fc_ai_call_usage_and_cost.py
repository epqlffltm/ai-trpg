"""ai call usage and cost

Revision ID: a3ee72e466fc
Revises: fb7d38de283c
Create Date: 2026-10-17 11:49:48.182250

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3ee72e466fc'
down_revision: str | Sequence[str] | None = 'fb7d38de283c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# AI 호출의 기록에 자세한 사용량과 원가의 칸을 더한다(app/ai/costs.py, #332).
# 캐시에서 읽은 입력, 캐시에 쓴 입력, 생각에 쓴 출력의 토큰 수, 모델 목록의 이름표,
# 그날의 단가로 센 원가와 그 단가의 줄.
# 모두 비워 둘 수 있다. 이 칸이 생기기 전의 줄과 모델 목록에 없는 모델의 줄은 비어 있다.
# 조건의 글자는 모델(app/ai/models.py)과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
TOKEN_DETAILS = 'cached_input_tokens >= 0 AND cache_write_tokens >= 0 AND reasoning_tokens >= 0'
COST = 'cost_usd >= 0'


def upgrade() -> None:
    op.add_column('ai_invocations', sa.Column('cached_input_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_invocations', sa.Column('cache_write_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_invocations', sa.Column('reasoning_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_invocations', sa.Column('model_slug', sa.String(length=48), nullable=True))
    op.add_column('ai_invocations', sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True))
    op.add_column('ai_invocations', sa.Column('cost_id', sa.Integer(), nullable=True))
    op.create_check_constraint(op.f('ck_ai_invocations_token_details_not_negative'), 'ai_invocations', TOKEN_DETAILS)
    op.create_check_constraint(op.f('ck_ai_invocations_cost_not_negative'), 'ai_invocations', COST)


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ai_invocations_cost_not_negative'), 'ai_invocations', type_='check')
    op.drop_constraint(op.f('ck_ai_invocations_token_details_not_negative'), 'ai_invocations', type_='check')
    op.drop_column('ai_invocations', 'cost_id')
    op.drop_column('ai_invocations', 'cost_usd')
    op.drop_column('ai_invocations', 'model_slug')
    op.drop_column('ai_invocations', 'reasoning_tokens')
    op.drop_column('ai_invocations', 'cache_write_tokens')
    op.drop_column('ai_invocations', 'cached_input_tokens')
