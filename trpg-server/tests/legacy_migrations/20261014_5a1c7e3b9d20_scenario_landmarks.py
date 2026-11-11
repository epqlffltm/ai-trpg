"""scenario landmarks

Revision ID: 5a1c7e3b9d20
Revises: d9895d38da07
Create Date: 2026-10-14 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '5a1c7e3b9d20'
down_revision: str | Sequence[str] | None = 'd9895d38da07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 길의 hidden(참, 거짓)을 visibility(open, fog, hidden)로 바꾼다. 길의 순서는 그대로다
ROUTES_TO_VISIBILITY = """
UPDATE scenarios SET routes = (
    SELECT jsonb_agg(
        (route - 'hidden')
        || jsonb_build_object('visibility', CASE WHEN (route->>'hidden')::boolean THEN 'hidden' ELSE 'open' END)
        ORDER BY position
    )
    FROM jsonb_array_elements(routes) WITH ORDINALITY AS listed(route, position)
)
WHERE jsonb_array_length(routes) > 0
"""

# 되돌릴 때는 숨긴 길만 hidden 이 참이다. 안개 길은 숨기지 않은 길로 돌아간다
ROUTES_TO_HIDDEN = """
UPDATE scenarios SET routes = (
    SELECT jsonb_agg(
        (route - 'visibility') || jsonb_build_object('hidden', route->>'visibility' = 'hidden')
        ORDER BY position
    )
    FROM jsonb_array_elements(routes) WITH ORDINALITY AS listed(route, position)
)
WHERE jsonb_array_length(routes) > 0
"""


def upgrade() -> None:
    # 있던 시나리오는 명소가 없다
    op.add_column(
        'scenarios', sa.Column('landmarks', postgresql.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"), nullable=False)
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_landmarks_count'), 'scenarios', 'cardinality(landmarks) <= 100')
    op.execute(ROUTES_TO_VISIBILITY)


def downgrade() -> None:
    op.execute(ROUTES_TO_HIDDEN)
    op.drop_constraint(op.f('ck_scenarios_landmarks_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'landmarks')
