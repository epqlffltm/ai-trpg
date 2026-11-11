"""wander monsters

Revision ID: b6e8a0c2d4f7
Revises: a4d6f8b0c2e5
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b6e8a0c2d4f7'
down_revision: str | Sequence[str] | None = 'a4d6f8b0c2e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 무작위 조우(#283)로 나온 마리는 기습을 스스로 갖는다. 있던 마리는 판의 조우에서 놓였으니 비어 있다


def upgrade() -> None:
    op.add_column('table_monsters', sa.Column('surprise', sa.String(length=20), nullable=True))
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_table_monsters_surprise_allowed'), 'table_monsters', "surprise IN ('none', 'monsters', 'party')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_monsters_surprise_allowed'), 'table_monsters', type_='check')
    op.drop_column('table_monsters', 'surprise')
