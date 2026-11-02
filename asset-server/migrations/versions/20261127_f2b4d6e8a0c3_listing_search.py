"""listing search

Revision ID: f2b4d6e8a0c3
Revises: d9f1b3c5e7a9
Create Date: 2026-11-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2b4d6e8a0c3'
down_revision: str | Sequence[str] | None = 'd9f1b3c5e7a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 이름으로 찾는 글자 조각 색인의 식과 연산자 묶음(extensions 스키마의 pg_trgm 것)
NAME = sa.literal_column("(document ->> 'name')").label('name')
NAME_OPS = {'name': 'extensions.gin_trgm_ops'}


def require_trgm() -> None:
    """
    pg_trgm 이 켜져 있지 않거나 asset 계정이 쓸 수 없으면 알아볼 수 있는 말로 멈춘다.

    asset 계정은 확장을 켤 수 없다(슈퍼유저만 된다). 그래서 여기서 켜지 않고, 쓸 수 있는지만 본다.
    아니면 아래의 gin_trgm_ops 가 "없는 연산자 묶음"이나 "권한 없음"이라는 알기 어려운 오류로 실패한다.
    """
    usable = op.get_bind().scalar(
        sa.text("SELECT has_schema_privilege('extensions', 'USAGE') FROM pg_extension WHERE extname = 'pg_trgm'")
    )
    if not usable:
        raise RuntimeError(
            'pg_trgm 이 켜져 있지 않거나 asset 계정이 extensions 스키마를 쓸 수 없습니다. '
            'docker/postgres/init/03-extensions.sql 과 asset 계정의 extensions 스키마 읽기 권한을 슈퍼유저로 실행하세요'
            '(asset-server/README.md 의 "준비")'
        )


def upgrade() -> None:
    require_trgm()
    op.create_index(
        'ix_character_versions_name_trgm',
        'character_versions',
        [NAME],
        postgresql_using='gin',
        postgresql_ops=NAME_OPS,
    )
    op.create_index(
        'ix_world_versions_name_trgm', 'world_versions', [NAME], postgresql_using='gin', postgresql_ops=NAME_OPS
    )


def downgrade() -> None:
    op.drop_index('ix_world_versions_name_trgm', table_name='world_versions')
    op.drop_index('ix_character_versions_name_trgm', table_name='character_versions')
