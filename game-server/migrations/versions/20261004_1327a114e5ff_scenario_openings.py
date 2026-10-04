"""scenario openings

Revision ID: 1327a114e5ff
Revises: bba6ecdc4659
Create Date: 2026-10-04 18:55:24.441175

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '1327a114e5ff'
down_revision: str | Sequence[str] | None = 'bba6ecdc4659'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 새 칸을 만든다. 이미 있는 행이 있으므로 잠깐 기본값을 둔다
    op.add_column('scenarios', sa.Column('openings', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False))
    # 2. 옛 도입부를 첫 번째 스타팅으로 옮긴다. 비어 있던 것은 옮기지 않는다
    op.execute("UPDATE scenarios SET openings = ARRAY[opening] WHERE btrim(opening) <> ''")
    # 3. 기본값을 뗀다. 모델과 같은 모양이 된다
    op.alter_column('scenarios', 'openings', server_default=None)
    # 4. 새 칸의 조건을 건다. 자동 생성은 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_openings_count'), 'scenarios', 'cardinality(openings) <= 5')
    op.create_check_constraint(
        op.f('ck_scenarios_openings_length'), 'scenarios', "char_length(array_to_string(openings, '')) <= 10000"
    )
    # 5. 옛 칸을 지운다. 칸에 걸린 조건(opening_length)도 함께 지워진다
    op.drop_column('scenarios', 'opening')


def downgrade() -> None:
    op.add_column('scenarios', sa.Column('opening', sa.Text(), server_default='', nullable=False))
    # 첫 번째 스타팅만 되돌아간다. 나머지는 사라진다
    op.execute('UPDATE scenarios SET opening = left(openings[1], 2000) WHERE cardinality(openings) > 0')
    op.alter_column('scenarios', 'opening', server_default=None)
    op.create_check_constraint(op.f('ck_scenarios_opening_length'), 'scenarios', 'char_length(opening) <= 2000')
    op.drop_column('scenarios', 'openings')
