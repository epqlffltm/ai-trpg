"""listing search

Revision ID: e1a3c5e7f9b2
Revises: d7e9f1a3b5c7
Create Date: 2026-11-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1a3c5e7f9b2'
down_revision: str | Sequence[str] | None = 'd7e9f1a3b5c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def require_trgm() -> None:
    """
    pg_trgm 이 켜져 있지 않으면 알아볼 수 있는 말로 멈춘다.

    게임 계정은 확장을 켤 수 없다(슈퍼유저만 된다). 그래서 여기서 켜지 않고, 켜져 있는지만 본다.
    켜져 있지 않으면 아래의 gin_trgm_ops 가 "없는 연산자 묶음"이라는 알기 어려운 오류로 실패한다.
    """
    found = op.get_bind().scalar(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
    if found is None:
        raise RuntimeError(
            'pg_trgm 이 켜져 있지 않습니다. docker/postgres/init/03-extensions.sql 을 슈퍼유저로 실행하세요'
            '(trpg-server/README.md 의 "준비")'
        )


def upgrade() -> None:
    require_trgm()
    op.create_index(
        'ix_assets_title_trgm',
        'assets',
        ['title'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'title': 'extensions.gin_trgm_ops'},
    )
    op.create_index(
        'ix_listings_tagline_trgm',
        'listings',
        ['tagline'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'tagline': 'extensions.gin_trgm_ops'},
    )


def downgrade() -> None:
    op.drop_index('ix_listings_tagline_trgm', table_name='listings', postgresql_using='gin')
    op.drop_index('ix_assets_title_trgm', table_name='assets', postgresql_using='gin')
