"""round auto retries

Revision ID: a57c4e086d8d
Revises: ef3e08670184
Create Date: 2026-10-16 14:39:56.596433

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a57c4e086d8d'
down_revision: str | Sequence[str] | None = 'ef3e08670184'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 라운드에 서버가 스스로 서술을 다시 맡긴 횟수(#275, app/rounds/recovery.py)를 적는 칸을 더한다.
# 지금까지의 라운드는 0 이다. 닫는 중인 채로 남은 라운드도 0 부터 센다


def upgrade() -> None:
    op.add_column(
        'table_rounds', sa.Column('auto_retries', sa.SmallInteger(), server_default=sa.text('0'), nullable=False)
    )
    op.create_check_constraint(op.f('ck_table_rounds_auto_retries_not_negative'), 'table_rounds', 'auto_retries >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_rounds_auto_retries_not_negative'), 'table_rounds', type_='check')
    op.drop_column('table_rounds', 'auto_retries')
