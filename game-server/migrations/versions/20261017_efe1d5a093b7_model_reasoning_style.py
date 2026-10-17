"""model reasoning style

Revision ID: efe1d5a093b7
Revises: a3ee72e466fc
Create Date: 2026-10-17 12:31:33.028725

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'efe1d5a093b7'
down_revision: str | Sequence[str] | None = 'a3ee72e466fc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록에 생각(thinking)을 켜고 끄는 방식(reasoning_style)의 칸을 더한다(app/catalog/models.py, #332).
# anthropic 창구의 모델만 적는다. 지금 있는 모델은 OpenAI 와 서버 곁의 모델뿐이라 비워 둔다.
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
REASONING_STYLES = "reasoning_style IS NULL OR reasoning_style IN ('adaptive', 'always', 'between_tools', 'budget')"


def upgrade() -> None:
    op.add_column('ai_models', sa.Column('reasoning_style', sa.String(length=20), nullable=True))
    op.create_check_constraint(op.f('ck_ai_models_reasoning_style_allowed'), 'ai_models', REASONING_STYLES)


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ai_models_reasoning_style_allowed'), 'ai_models', type_='check')
    op.drop_column('ai_models', 'reasoning_style')
