# game-server/app/listings/models.py

"""
공개 정보의 테이블 모델. 시나리오를 남에게 보이게 하고 알리는 데 쓰는 것이다.

시나리오(초안)와 판(굳힌 것)은 "무엇을 플레이하는가"다. 공개 정보는 "어떻게 알리는가"다.
둘을 나눠 둔다. 판을 새로 내지 않고도 한줄소개와 태그를 고칠 수 있다.

공개 정보는 자산이 아니다. 시나리오에 하나씩 딸려 있고, 주인과 지운 시각은 시나리오의 것을 따른다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import Rating, at_most, one_of
from app.core.database import Base

# 글의 길이 제한(글자 수)
TAGLINE_MAX_LENGTH = 100
LISTING_DESCRIPTION_MAX_LENGTH = 5000

# 시나리오 하나에 고를 수 있는 장르의 수. 전부 고르면 장르가 뜻을 잃는다
LISTING_MAX_GENRES = 3

# 제작자가 자유롭게 적는 태그
LISTING_MAX_TAGS = 10
TAG_MAX_LENGTH = 20


class Genre(enum.StrEnum):
    """
    장르. 운영자가 정한 목록에서 고른다. 제작자가 자유롭게 적는 것은 태그다.

    목록을 바꾸려면 여기를 고쳐 배포한다. 값은 주소와 저장에 쓰는 이름이고, 화면에 보이는 말은 화면이 정한다.
    등급(성인용)은 장르가 아니다. 시나리오의 등급에서 온다.
    """

    # 이야기의 종류
    FANTASY = 'fantasy'  # 판타지
    WUXIA = 'wuxia'  # 무협. 동양판타지를 포함한다
    URBAN_FANTASY = 'urban_fantasy'  # 현대판타지
    SF = 'sf'
    APOCALYPSE = 'apocalypse'  # 아포칼립스
    HORROR = 'horror'  # 공포
    MYSTERY = 'mystery'  # 추리
    ROMANCE = 'romance'  # 로맨스
    SLICE_OF_LIFE = 'slice_of_life'  # 일상
    ALT_HISTORY = 'alt_history'  # 대체역사
    COMEDY = 'comedy'  # 개그

    # 누구를 위한 이야기인가
    FOR_MEN = 'for_men'  # 남성향
    FOR_WOMEN = 'for_women'  # 여성향


class Listing(Base):
    """
    시나리오 하나의 공개 정보. 소개 페이지의 내용과, 지금 공개 중인 판을 담는다.

    version_id 가 비어 있으면 공개하지 않은 것이다. 소개 페이지는 공개하기 전에도 미리 써 둘 수 있다.
    시나리오 하나에 공개 판은 하나다. 다른 판을 공개하면 앞의 것과 바뀐다.
    """

    __tablename__ = 'listings'
    __table_args__ = (
        CheckConstraint(at_most('description', LISTING_DESCRIPTION_MAX_LENGTH), name='description_length'),
        CheckConstraint(f'cardinality(genres) <= {LISTING_MAX_GENRES}', name='genres_count'),
        CheckConstraint(f'cardinality(tags) <= {LISTING_MAX_TAGS}', name='tags_count'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        # 공개 중이면 공개한 시각이 있고, 아니면 없다. 둘이 어긋난 행이 생기지 않는다
        CheckConstraint('(version_id IS NULL) = (published_at IS NULL)', name='published_together'),
    )

    # 기본 키이면서 시나리오를 가리킨다. 시나리오 하나에 공개 정보가 둘 붙을 수 없다
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('scenarios.asset_id', ondelete='CASCADE'), primary_key=True
    )

    # 지금 공개 중인 판. 비어 있으면 공개하지 않은 것이다. 공개 중인 판의 행은 지울 수 없다
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('scenario_versions.id', ondelete='RESTRICT'), index=True
    )

    # 공개 중인 판의 등급. 판을 고를 때 서버가 판에서 읽어 적는다. 제작자가 직접 적지 않는다.
    # 초안의 등급을 쓰지 않는다. 초안을 전체 이용가로 바꿔도 공개 중인 성인용 판이 전체 이용가로 보이면 안 된다
    rating: Mapped[str] = mapped_column(String(20), default=Rating.ALL)

    # 공개한 시각. 목록을 최근에 공개한 순서로 보여 줄 때 쓴다
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # 한줄소개. 목록에 보인다
    tagline: Mapped[str] = mapped_column(String(TAGLINE_MAX_LENGTH), default='')

    # 소개글. 소개 페이지의 본문이다. 지금은 꾸밈 없는 글이다
    description: Mapped[str] = mapped_column(Text, default='')

    # 장르. Genre 의 값들이다. 허용 값의 검사는 입력의 모양(schemas.py)이 한다.
    # DB 의 CHECK 로 걸지 않는다. 장르 목록을 바꿀 때마다 마이그레이션이 필요해진다
    genres: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)

    # 태그. 제작자가 자유롭게 적는다
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(TAG_MAX_LENGTH)), default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
