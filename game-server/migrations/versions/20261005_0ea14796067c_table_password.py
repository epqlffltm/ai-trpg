"""table password

Revision ID: 0ea14796067c
Revises: e6fe35d7175c
Create Date: 2026-10-05 00:51:32.574988

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0ea14796067c'
down_revision: str | Sequence[str] | None = 'e6fe35d7175c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 새 칸은 비어 있어도 되므로 기본값이 필요 없다. 이미 있는 테이블은 비밀번호가 없는 것이 된다
    op.add_column('game_tables', sa.Column('password_hash', sa.String(length=200), nullable=True))
    # 자동 생성은 CHECK 를 찾지 못한다
    op.create_check_constraint(
        op.f('ck_game_tables_password_needs_public'), 'game_tables', 'password_hash IS NULL OR is_public'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_game_tables_password_needs_public'), 'game_tables', type_='check')
    op.drop_column('game_tables', 'password_hash')
