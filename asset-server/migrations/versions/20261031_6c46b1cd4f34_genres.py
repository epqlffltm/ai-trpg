"""genres

Revision ID: 6c46b1cd4f34
Revises: b6d8f0a2c4e5
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6c46b1cd4f34'
down_revision: str | Sequence[str] | None = 'b6d8f0a2c4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터와 세계관의 장르(app/genres.py, 판의 형식 캐릭터 9·세계관 4). 하나이고 비울 수 있다. 있던 것은 비어 있다.
# 허용 값은 입력의 모양이 본다. DB 의 CHECK 로 걸지 않는다(목록을 바꿀 때마다 마이그레이션이 필요해진다)


def upgrade() -> None:
    op.add_column('characters', sa.Column('genre', sa.String(length=30), nullable=True))
    op.add_column('worlds', sa.Column('genre', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('worlds', 'genre')
    op.drop_column('characters', 'genre')
