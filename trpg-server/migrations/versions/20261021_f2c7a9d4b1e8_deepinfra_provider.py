"""deepinfra provider

Revision ID: f2c7a9d4b1e8
Revises: e6b1a4c8d2f7
Create Date: 2026-10-21 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = 'f2c7a9d4b1e8'
down_revision: str | Sequence[str] | None = 'e6b1a4c8d2f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록에 DeepInfra 창구(deepinfra)를 더한다(app/ai/catalog_contract.py, #398).
# CHECK 의 글자만 바꾼다. 지금 있는 줄은 옛 값뿐이라 그대로 맞는다.
# 조건의 글자는 모델과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
PROVIDER = 'ck_ai_models_provider_allowed'
OLD_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai')"
NEW_PROVIDERS = "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai', 'deepinfra')"


def replace_check(name: str, rule: str) -> None:
    """CHECK 하나를 새 조건으로 바꾼다."""
    op.drop_constraint(op.f(name), 'ai_models', type_='check')
    op.create_check_constraint(op.f(name), 'ai_models', rule)


def upgrade() -> None:
    replace_check(PROVIDER, NEW_PROVIDERS)


def downgrade() -> None:
    # deepinfra 창구가 적힌 줄이 있으면 되돌릴 수 없다(CHECK 가 막는다). 그 모델들을 먼저 지운다
    replace_check(PROVIDER, OLD_PROVIDERS)
