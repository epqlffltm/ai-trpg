"""round prices

Revision ID: 2e6b8d4f9a3c
Revises: 7c3a9e5b2d1f
Create Date: 2026-10-18 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '2e6b8d4f9a3c'
down_revision: str | Sequence[str] | None = '7c3a9e5b2d1f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 라운드를 열 때 알린 1인 1라운드의 값과, 사람마다 실제로 홀드한 값을 적는 칸을 더한다(#379).
# 값은 결제 서버가 준 글자 그대로다(셈하지 않는다). 있던 라운드와 청구는 비어 있다(알리지 않았다)


def upgrade() -> None:
    op.add_column('table_rounds', sa.Column('announced_credits', sa.String(length=32), nullable=True))
    op.add_column('table_rounds', sa.Column('announced_tier', sa.String(length=20), nullable=True))
    op.add_column('narration_charges', sa.Column('held_credits', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('narration_charges', 'held_credits')
    op.drop_column('table_rounds', 'announced_tier')
    op.drop_column('table_rounds', 'announced_credits')
