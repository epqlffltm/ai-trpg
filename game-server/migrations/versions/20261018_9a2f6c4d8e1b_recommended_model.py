"""recommended model

Revision ID: 9a2f6c4d8e1b
Revises: 6d1e8b3a9c4f
Create Date: 2026-10-18 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9a2f6c4d8e1b'
down_revision: str | Sequence[str] | None = '6d1e8b3a9c4f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 시나리오의 추천 서술 모델과 회사마다의 대체 모델을 더하고, 서술 등급을 걷어낸다(#332 의 뒤).
#   - ai_models.vendor_fallback: 운영자가 정한 그 회사의 대체 모델. 회사마다 하나뿐이다(부분 유일 색인).
#   - scenarios.narration_model: 추천 서술 모델. 있던 시나리오는 비어 있다. 고칠 때 함께 정해야 저장된다.
#   - game_tables, table_rounds 의 narration_tier 를 지운다. 등급의 CHECK 도 칸과 함께 지워진다.
#     서술 모델이 없는 옛 테이블과 라운드는 서버의 기본 모델과 옛 가격표(narration.standard)로 이어 간다.
#     등급이 premium 이던 옛 테이블도 그렇게 된다. 운영 전이라 그런 테이블이 없다.
# 되돌리면 등급은 모두 standard 로 돌아온다. 무엇이었는지는 남지 않는다

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
TIERS = "'standard', 'premium'"
TABLES = ('game_tables', 'table_rounds')


def upgrade() -> None:
    op.add_column(
        'ai_models', sa.Column('vendor_fallback', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.create_index(
        'uq_ai_models_vendor_fallback',
        'ai_models',
        ['vendor'],
        unique=True,
        postgresql_where=sa.text('vendor_fallback'),
    )
    op.add_column('scenarios', sa.Column('narration_model', sa.String(length=48), nullable=True))
    for table in TABLES:
        op.drop_column(table, 'narration_tier')


def downgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('narration_tier', sa.String(length=20), server_default=sa.text("'standard'"), nullable=False),
        )
        op.create_check_constraint(op.f(f'ck_{table}_narration_tier_allowed'), table, f'narration_tier IN ({TIERS})')
    op.drop_column('scenarios', 'narration_model')
    op.drop_index('uq_ai_models_vendor_fallback', table_name='ai_models', postgresql_where=sa.text('vendor_fallback'))
    op.drop_column('ai_models', 'vendor_fallback')
