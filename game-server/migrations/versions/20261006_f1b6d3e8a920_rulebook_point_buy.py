"""rulebook point buy

Revision ID: f1b6d3e8a920
Revises: e3a9c1d5b7f2
Create Date: 2026-10-06 21:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1b6d3e8a920'
down_revision: str | Sequence[str] | None = 'e3a9c1d5b7f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 값. 점수제의 총점과 값표다.
# 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
POINT_BUY = {
    'budget': 27,
    'costs': [
        {'score': 8, 'cost': 0},
        {'score': 9, 'cost': 1},
        {'score': 10, 'cost': 2},
        {'score': 11, 'cost': 3},
        {'score': 12, 'cost': 4},
        {'score': 13, 'cost': 5},
        {'score': 14, 'cost': 7},
        {'score': 15, 'cost': 9},
    ],
}


def upgrade() -> None:
    # 표의 모양은 그대로다. rules 문서 안에 칸 하나를 더한다. 그래서 자동 생성으로는 아무것도 나오지 않는다.
    # 이미 그 칸이 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다.
    # 값이 null 인 칸과 칸이 없는 것은 다르다. null 은 "이 규칙에는 점수제가 없다"는 뜻이라 그대로 둔다
    fill = sa.text(
        "UPDATE rulebooks SET rules = rules || jsonb_build_object('point_buy', CAST(:point_buy AS JSONB)) "
        "WHERE NOT jsonb_exists(rules, 'point_buy')"
    )
    op.execute(fill.bindparams(point_buy=json.dumps(POINT_BUY)))


def downgrade() -> None:
    # 문서에서 그 칸만 뺀다
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'point_buy'"))
