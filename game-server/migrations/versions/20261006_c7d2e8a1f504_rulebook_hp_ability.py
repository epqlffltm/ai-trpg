"""rulebook hp ability

Revision ID: c7d2e8a1f504
Revises: b4f1c2a97d30
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d2e8a1f504'
down_revision: str | Sequence[str] | None = 'b4f1c2a97d30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 값. 최대 HP 에 보정을 더하는 능력치다.
# 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
HP_ABILITY = 'con'


def upgrade() -> None:
    # 표의 모양은 그대로다. rules 문서 안에 칸 하나를 더한다. 그래서 자동 생성으로는 아무것도 나오지 않는다.
    # 이미 그 칸이 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다.
    # 값이 null 인 칸과 칸이 없는 것은 다르다. null 은 "능력치가 HP 에 닿지 않는다"는 뜻이라 그대로 둔다
    fill = sa.text(
        "UPDATE rulebooks SET rules = rules || jsonb_build_object('hp_ability', CAST(:hp_ability AS TEXT)) "
        "WHERE NOT jsonb_exists(rules, 'hp_ability')"
    )
    op.execute(fill.bindparams(hp_ability=HP_ABILITY))


def downgrade() -> None:
    # 문서에서 그 칸만 뺀다
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'hp_ability'"))
