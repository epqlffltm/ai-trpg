"""zai provider

Revision ID: 4b8e2d7f1a6c
Revises: 9a2f6c4d8e1b
Create Date: 2026-10-18 23:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = '4b8e2d7f1a6c'
down_revision: str | Sequence[str] | None = '9a2f6c4d8e1b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록에 Z.ai 창구(zai)와 생각의 방식 thinking_type 을 더한다(app/catalog/models.py, #378).
# CHECK 의 글자만 바꾼다. 지금 있는 줄은 옛 값뿐이라 그대로 맞는다.
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
PROVIDER = 'ck_ai_models_provider_allowed'
OLD_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local')"
NEW_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai')"

STYLE = 'ck_ai_models_reasoning_style_allowed'
OLD_STYLES = "'adaptive', 'always', 'between_tools', 'budget', 'level_minimal', 'level_low', 'budget_min'"
OLD_STYLE_RULE = f'reasoning_style IS NULL OR reasoning_style IN ({OLD_STYLES})'
NEW_STYLE_RULE = f"reasoning_style IS NULL OR reasoning_style IN ({OLD_STYLES}, 'thinking_type')"


def replace_check(name: str, rule: str) -> None:
    """CHECK 하나를 새 조건으로 바꾼다."""
    op.drop_constraint(op.f(name), 'ai_models', type_='check')
    op.create_check_constraint(op.f(name), 'ai_models', rule)


def upgrade() -> None:
    replace_check(PROVIDER, NEW_PROVIDERS)
    replace_check(STYLE, NEW_STYLE_RULE)


def downgrade() -> None:
    # zai 창구나 thinking_type 이 적힌 줄이 있으면 되돌릴 수 없다(CHECK 가 막는다). 그 모델들을 먼저 지운다
    replace_check(STYLE, OLD_STYLE_RULE)
    replace_check(PROVIDER, OLD_PROVIDERS)
