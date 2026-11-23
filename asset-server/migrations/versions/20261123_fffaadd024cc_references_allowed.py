"""references allowed

Revision ID: fffaadd024cc
Revises: 515a58e78e7f
Create Date: 2026-11-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'fffaadd024cc'
down_revision: str | Sequence[str] | None = '515a58e78e7f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료(SRD, 위키백과)를 chat 의 대화와 story 의 세션에 섞어도 되는가(제작자가 정한다).
#   - characters.references_allowed, worlds.references_allowed. 있던 것은 허용하지 않는다(false)
# 되돌리면 칸을 지운다. 이미 게시한 판의 문서에 적힌 값은 그대로다


def upgrade() -> None:
    for table in ('characters', 'worlds'):
        op.add_column(table, sa.Column('references_allowed', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    for table in ('worlds', 'characters'):
        op.drop_column(table, 'references_allowed')
