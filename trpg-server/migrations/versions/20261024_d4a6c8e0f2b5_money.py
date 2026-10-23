"""money

Revision ID: d4a6c8e0f2b5
Revises: c3f5a7e9b1d2
Create Date: 2026-10-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd4a6c8e0f2b5'
down_revision: str | Sequence[str] | None = 'c3f5a7e9b1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 돈(#278). 시나리오의 화폐와 캐릭터의 돈이다. 있던 시나리오는 화폐가 없고, 있던 캐릭터의 돈은 0 이다.
# 앱의 코드를 가져오지 않는다(MONEY_MAX 1,000,000)
MONEY_MAX = 1_000_000


def upgrade() -> None:
    op.add_column('scenarios', sa.Column('currency', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('table_sheets', sa.Column('money', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint(op.f('ck_table_sheets_money_range'), 'table_sheets', f'money BETWEEN 0 AND {MONEY_MAX}')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_sheets_money_range'), 'table_sheets', type_='check')
    op.drop_column('table_sheets', 'money')
    op.drop_column('scenarios', 'currency')
