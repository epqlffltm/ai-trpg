"""lore entry kind

Revision ID: e8a0c2d4f6b8
Revises: d6f8b0c2e4a6
Create Date: 2026-10-11 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e8a0c2d4f6b8'
down_revision: str | Sequence[str] | None = 'd6f8b0c2e4a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
KINDS = "'person', 'place', 'item', 'faction', 'species', 'legend', 'event', 'other'"


def upgrade() -> None:
    # 칸은 자동 생성이 찾은 그대로다. 있던 항목은 기타로 채운다. 종류가 생기기 전에는 모두 같은 모양이었다
    op.add_column(
        'lore_entries',
        sa.Column('kind', sa.String(length=20), server_default=sa.text("'other'"), nullable=False),
    )
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(op.f('ck_lore_entries_kind_allowed'), 'lore_entries', f'kind IN ({KINDS})')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_lore_entries_kind_allowed'), 'lore_entries', type_='check')
    op.drop_column('lore_entries', 'kind')
