"""unlisted

Revision ID: a3c5e7f9b1d4
Revises: f2b4d6e8a0c3
Create Date: 2026-11-28 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = 'a3c5e7f9b1d4'
down_revision: str | Sequence[str] | None = 'f2b4d6e8a0c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 링크 공개(#993)를 공개 범위의 값으로 받는다. 자동 생성은 CHECK 의 글이 바뀐 것을 찾지 못해 손으로 쓴다
TABLES = ('characters', 'worlds')
WITH_UNLISTED = "visibility IN ('private', 'public', 'unlisted')"
WITHOUT_UNLISTED = "visibility IN ('private', 'public')"


def replace_check(condition: str) -> None:
    """두 테이블의 공개 범위 CHECK 를 condition 으로 바꾼다."""
    for table in TABLES:
        op.drop_constraint('visibility_allowed', table, type_='check')
        op.create_check_constraint('visibility_allowed', table, condition)


def upgrade() -> None:
    replace_check(WITH_UNLISTED)


def downgrade() -> None:
    # 링크 공개였던 것은 비공개로 돌린다. 공개로 돌리면 목록에 나오게 된다
    for table in TABLES:
        op.execute(f"UPDATE {table} SET visibility = 'private' WHERE visibility = 'unlisted'")
    replace_check(WITHOUT_UNLISTED)
