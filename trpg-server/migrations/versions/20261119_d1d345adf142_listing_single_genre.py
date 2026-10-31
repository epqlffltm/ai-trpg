"""listing single genre

Revision ID: d1d345adf142
Revises: f9b1d3e5a7c0
Create Date: 2026-11-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd1d345adf142'
down_revision: str | Sequence[str] | None = 'f9b1d3e5a7c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 시나리오의 장르를 하나로 줄인다. 장르가 플레이 화면과 소개 화면의 테마를 정하게 되어,
# 여럿이면 어느 것을 따를지 모른다.
# 장르 목록(genres, 3 개까지)을 장르 하나(genre)로 바꾼다.
# 남성향·여성향(for_men, for_women)은 장르에서 빠지고 태그가 된다.
# - genre: 목록에서 남성향·여성향을 뺀 첫 장르. 그런 장르가 없었으면 판타지(FILL)로 채운다. 장르는 반드시 있다(NOT NULL)
# - tags: 남성향·여성향이 있었으면 같은 뜻의 태그('남성향', '여성향')를 끝에 더한다.
#   이미 있거나 태그가 10 개로 차 있으면 더하지 않는다
# 되돌리면 genre 를 하나짜리 목록으로 옮긴다. 더한 태그와, 하나로 줄이며 버린 장르는 되살리지 않는다

AUDIENCE_TAGS = (('for_men', '남성향'), ('for_women', '여성향'))
FILL = 'fantasy'


def upgrade() -> None:
    op.add_column('listings', sa.Column('genre', sa.String(length=30), nullable=True))
    op.execute(
        """
        UPDATE listings SET genre = (
            SELECT kept.value FROM unnest(genres) WITH ORDINALITY AS kept(value, position)
            WHERE kept.value NOT IN ('for_men', 'for_women')
            ORDER BY kept.position LIMIT 1
        )
        """
    )
    for genre, tag in AUDIENCE_TAGS:
        op.execute(
            sa.text(
                """
                UPDATE listings SET tags = array_append(tags, CAST(:tag AS varchar(20)))
                WHERE :genre = ANY(genres) AND NOT (CAST(:tag AS varchar(20)) = ANY(tags)) AND cardinality(tags) < 10
                """
            ).bindparams(genre=genre, tag=tag)
        )
    op.execute(sa.text('UPDATE listings SET genre = :fill WHERE genre IS NULL').bindparams(fill=FILL))
    op.alter_column('listings', 'genre', nullable=False)
    op.create_index(op.f('ix_listings_genre'), 'listings', ['genre'], unique=False)
    op.drop_constraint(op.f('ck_listings_genres_count'), 'listings', type_='check')
    op.drop_column('listings', 'genres')


def downgrade() -> None:
    op.add_column(
        'listings',
        sa.Column('genres', postgresql.ARRAY(sa.String(length=30)), server_default='{}', nullable=False),
    )
    op.alter_column('listings', 'genres', server_default=None)
    op.execute('UPDATE listings SET genres = ARRAY[genre]')
    op.create_check_constraint(op.f('ck_listings_genres_count'), 'listings', 'cardinality(genres) <= 3')
    op.drop_index(op.f('ix_listings_genre'), table_name='listings')
    op.drop_column('listings', 'genre')
