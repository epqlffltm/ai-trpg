"""copied from references

Revision ID: e5b9c3a7d1f4
Revises: d7a3c9e5f2b8
Create Date: 2026-10-21 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b9c3a7d1f4'
down_revision: str | Sequence[str] | None = 'd7a3c9e5f2b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료에서 복사한 로어북 항목과 몬스터의 출처(#482 4단계, app/references/copying.py).
# 지금의 행은 직접 쓴 것이라 비어 있다
TABLES = ('lore_entries', 'monsters')
PAIRED = '(copied_source IS NULL) = (copied_key IS NULL)'


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('copied_source', sa.String(length=20), nullable=True))
        op.add_column(table, sa.Column('copied_key', sa.String(length=100), nullable=True))
        op.create_check_constraint(op.f(f'ck_{table}_copied_from_paired'), table, PAIRED)


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f'ck_{table}_copied_from_paired'), table, type_='check')
        op.drop_column(table, 'copied_key')
        op.drop_column(table, 'copied_source')
