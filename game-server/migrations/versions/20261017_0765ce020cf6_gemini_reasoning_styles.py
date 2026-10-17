"""gemini reasoning styles

Revision ID: 0765ce020cf6
Revises: efe1d5a093b7
Create Date: 2026-10-17 13:34:20.759659

"""

from collections.abc import Sequence

from alembic import op

revision: str = '0765ce020cf6'
down_revision: str | Sequence[str] | None = 'efe1d5a093b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 생각을 켜고 끄는 방식에 Gemini 의 값(level_minimal, level_low, budget_min)을 더한다(app/catalog/models.py, #332).
# CHECK 의 글자만 바꾼다. 지금 있는 줄은 Claude 의 값뿐이라 그대로 맞는다.
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
NAME = 'ck_ai_models_reasoning_style_allowed'
CLAUDE = "'adaptive', 'always', 'between_tools', 'budget'"
GEMINI = "'level_minimal', 'level_low', 'budget_min'"
WITH_GEMINI = f'reasoning_style IS NULL OR reasoning_style IN ({CLAUDE}, {GEMINI})'
CLAUDE_ONLY = f'reasoning_style IS NULL OR reasoning_style IN ({CLAUDE})'


def upgrade() -> None:
    op.drop_constraint(op.f(NAME), 'ai_models', type_='check')
    op.create_check_constraint(op.f(NAME), 'ai_models', WITH_GEMINI)


def downgrade() -> None:
    # Gemini 의 값이 적힌 줄이 있으면 되돌릴 수 없다(CHECK 가 막는다). 그 모델들을 먼저 지우거나 값을 바꾼다
    op.drop_constraint(op.f(NAME), 'ai_models', type_='check')
    op.create_check_constraint(op.f(NAME), 'ai_models', CLAUDE_ONLY)
