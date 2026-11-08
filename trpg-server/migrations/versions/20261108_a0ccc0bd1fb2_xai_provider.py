"""xai provider

Revision ID: a0ccc0bd1fb2
Revises: f2c7a9d4b1e8
Create Date: 2026-11-08 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = 'a0ccc0bd1fb2'
down_revision: str | Sequence[str] | None = 'f2c7a9d4b1e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록에 xAI 창구(xai, Grok)를 더한다(shared/ai-core 의 ai_core/catalog_contract.py).
# CHECK 의 글자만 바꾼다. 지금 있는 줄은 옛 값뿐이라 그대로 맞는다.
# 이 CHECK 를 마지막으로 바꾼 리비전(f2c7a9d4b1e8)에서 갈라진다.
# 다른 마이그레이션의 차례에 기대지 않는다(upgrade heads).
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
PROVIDER = 'ck_ai_models_provider_allowed'
OLD_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai', 'deepinfra')"
NEW_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai', 'deepinfra', 'xai')"


def replace_check(name: str, rule: str) -> None:
    """CHECK 하나를 새 조건으로 바꾼다."""
    op.drop_constraint(op.f(name), 'ai_models', type_='check')
    op.create_check_constraint(op.f(name), 'ai_models', rule)


def upgrade() -> None:
    replace_check(PROVIDER, NEW_PROVIDERS)


def downgrade() -> None:
    # xai 창구가 적힌 줄이 있으면 되돌릴 수 없다(CHECK 가 막는다). 그 모델들을 먼저 지운다
    replace_check(PROVIDER, OLD_PROVIDERS)
