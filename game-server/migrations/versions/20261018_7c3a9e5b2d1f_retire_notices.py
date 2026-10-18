"""retire notices

Revision ID: 7c3a9e5b2d1f
Revises: 4b8e2d7f1a6c
Create Date: 2026-10-18 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7c3a9e5b2d1f'
down_revision: str | Sequence[str] | None = '4b8e2d7f1a6c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블의 서술 모델의 은퇴를 어디까지 알렸는지 적는 칸을 더한다(app/tables/model_retirement.py).
# 은퇴일과, 알린 단계(30, 14, 7, 1 일 전, 대신할 모델이 없다고 알렸으면 0). 있던 테이블은 비어 있다(아직 알리지 않았다)


def upgrade() -> None:
    op.add_column('game_tables', sa.Column('retire_notice_for', sa.Date(), nullable=True))
    op.add_column('game_tables', sa.Column('retire_notice_days', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('game_tables', 'retire_notice_days')
    op.drop_column('game_tables', 'retire_notice_for')
