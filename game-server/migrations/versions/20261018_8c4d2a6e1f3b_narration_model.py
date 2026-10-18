"""narration model

Revision ID: 8c4d2a6e1f3b
Revises: 5b2e9c41d7a3
Create Date: 2026-10-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '8c4d2a6e1f3b'
down_revision: str | Sequence[str] | None = '5b2e9c41d7a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블과 라운드에 방장이 고른 서술 모델(모델 목록의 이름표)을 더한다(#332).
# 테이블의 것은 방장이 고르고, 라운드의 것은 열 때 테이블의 것을 굳힌다.
# 비워 둘 수 있다. 비어 있으면 서버의 기본(서술 등급)으로 걸고 서술한다. 이 칸이 생기기 전의 줄은 비어 있다.
# 길이는 모델 목록의 이름표와 같다(48자). 외래 키는 두지 않는다. 고를 때 서버가 확인한다
SLUG_LENGTH = 48


def upgrade() -> None:
    op.add_column('game_tables', sa.Column('narration_model', sa.String(length=SLUG_LENGTH), nullable=True))
    op.add_column('table_rounds', sa.Column('narration_model', sa.String(length=SLUG_LENGTH), nullable=True))


def downgrade() -> None:
    op.drop_column('table_rounds', 'narration_model')
    op.drop_column('game_tables', 'narration_model')
