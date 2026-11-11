"""price code length

Revision ID: 6d1e8b3a9c4f
Revises: 3f7a9c1e5b2d
Create Date: 2026-10-18 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6d1e8b3a9c4f'
down_revision: str | Sequence[str] | None = '3f7a9c1e5b2d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 청구의 가격표 이름을 40자에서 64자로 늘린다(#332). 모델마다의 가격표 이름(narration.<이름표>.i0.o0)은
# 이름표가 48자까지라 64자까지 된다. 결제 서버의 가격표 이름의 상한(64자)과 맞춘다.
# 줄이는 쪽(downgrade)은 40자를 넘는 줄이 있으면 실패한다. 그런 줄이 없을 때만 되돌린다


def upgrade() -> None:
    op.alter_column('narration_charges', 'price_code', type_=sa.String(length=64), existing_type=sa.String(length=40))


def downgrade() -> None:
    op.alter_column('narration_charges', 'price_code', type_=sa.String(length=40), existing_type=sa.String(length=64))
