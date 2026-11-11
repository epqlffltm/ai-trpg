"""rulebook magnitudes

Revision ID: b4f1c2a97d30
Revises: 20a2740ca314
Create Date: 2026-10-06 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b4f1c2a97d30'
down_revision: str | Sequence[str] | None = '20a2740ca314'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 양의 등급.
# 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다.
# 앱의 코드를 가져오지 않고 값을 여기에 적어 둔다. 마이그레이션은 그때의 DB 를 그때의 값으로 고친 기록이고,
# 앱의 코드는 나중에 바뀔 수 있다
MAGNITUDES = [
    {'key': 'light', 'name': '가벼움', 'count': 1, 'sides': 4},
    {'key': 'moderate', 'name': '보통', 'count': 1, 'sides': 8},
    {'key': 'heavy', 'name': '심함', 'count': 2, 'sides': 8},
]


def upgrade() -> None:
    # 표의 모양은 그대로다. rules 문서 안에 칸 하나를 더한다. 그래서 자동 생성으로는 아무것도 나오지 않는다.
    # || 는 두 문서를 합친다. 이미 그 칸이 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다
    fill = sa.text(
        "UPDATE rulebooks SET rules = rules || jsonb_build_object('magnitudes', CAST(:magnitudes AS JSONB)) "
        "WHERE rules -> 'magnitudes' IS NULL"
    )
    op.execute(fill.bindparams(magnitudes=json.dumps(MAGNITUDES, ensure_ascii=False)))


def downgrade() -> None:
    # 문서에서 그 칸만 뺀다
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'magnitudes'"))
