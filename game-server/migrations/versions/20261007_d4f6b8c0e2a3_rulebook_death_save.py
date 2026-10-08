"""rulebook death save

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-10-07 14:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4f6b8c0e2a3'
down_revision: str | Sequence[str] | None = 'c3e5a7b9d1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 값. 죽음의 굴림이다.
# 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
DEATH_SAVE = {'target': 10, 'successes': 3, 'failures': 3}


def upgrade() -> None:
    # 표의 모양은 그대로다. rules 문서 안에 칸 하나를 더한다. 그래서 자동 생성으로는 아무것도 나오지 않는다.
    # 이미 그 칸이 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다.
    # 값이 null 인 칸과 칸이 없는 것은 다르다. null 은 "주사위가 캐릭터를 죽이지 않는다"는 뜻이라 그대로 둔다
    fill = sa.text(
        "UPDATE rulebooks SET rules = rules || jsonb_build_object('death_save', CAST(:death_save AS JSONB)) "
        "WHERE NOT jsonb_exists(rules, 'death_save')"
    )
    op.execute(fill.bindparams(death_save=json.dumps(DEATH_SAVE)))


def downgrade() -> None:
    # 문서에서 그 칸만 뺀다
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'death_save'"))
