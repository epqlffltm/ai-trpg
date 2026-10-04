# game-server/app/listings/schemas.py

"""
공개 정보 API 가 받는 입력과 내보내는 응답의 모양.

응답이 둘이다. 제작자가 자기 것을 볼 때(ListingDetail)와, 다른 사용자가 공개된 것을 볼 때(PublicListing)다.
어느 쪽에도 판의 굳힌 내용(GM 전용 글이 들어 있다)은 싣지 않는다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import Rating
from app.listings.models import (
    LISTING_DESCRIPTION_MAX_LENGTH,
    LISTING_MAX_GENRES,
    LISTING_MAX_TAGS,
    TAG_MAX_LENGTH,
    TAGLINE_MAX_LENGTH,
    Genre,
)


def reject_duplicate_genres(genres: list[Genre]) -> list[Genre]:
    """같은 장르가 두 번 있으면 거부한다."""
    if len(set(genres)) != len(genres):
        raise ValueError('같은 장르가 두 번 있습니다.')
    return genres


def reject_duplicate_tags(tags: list[str]) -> list[str]:
    """같은 태그가 두 번 있으면 거부한다. 대소문자만 다른 것도 같은 것으로 본다."""
    folded = [tag.casefold() for tag in tags]
    if len(set(folded)) != len(folded):
        raise ValueError('같은 태그가 두 번 있습니다.')
    return tags


Tagline = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TAGLINE_MAX_LENGTH)]
ListingDescription = Annotated[str, StringConstraints(max_length=LISTING_DESCRIPTION_MAX_LENGTH)]
Genres = Annotated[list[Genre], Field(max_length=LISTING_MAX_GENRES), AfterValidator(reject_duplicate_genres)]

# 태그 하나. 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TAG_MAX_LENGTH)]
Tags = Annotated[list[Tag], Field(max_length=LISTING_MAX_TAGS), AfterValidator(reject_duplicate_tags)]


class ListingUpdate(BaseModel):
    """
    소개 페이지를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    None 은 "보내지 않았다"는 뜻이다. 장르나 태그를 전부 없애려면 빈 목록을 보낸다.
    어느 판을 공개할지는 여기서 받지 않는다. 공개는 따로 하는 일이다(PublicationUpdate).
    """

    model_config = ConfigDict(extra='forbid')

    tagline: Tagline | None = None
    description: ListingDescription | None = None
    genres: Genres | None = None
    tags: Tags | None = None


class PublicationUpdate(BaseModel):
    """
    공개할 판을 정할 때 받는 값. 판의 번호를 적는다.

    비워서 보내면(null) 공개를 내린다.
    """

    model_config = ConfigDict(extra='forbid')

    version: int | None = Field(ge=1)


class ListingDetail(BaseModel):
    """제작자가 자기 시나리오의 공개 정보를 볼 때의 값."""

    scenario_id: uuid.UUID
    tagline: str
    description: str
    genres: list[Genre]
    tags: list[str]
    # 공개 중인 판의 번호. 공개하지 않았으면 None 이다
    version: int | None
    # 공개 중인 판의 등급. 공개하지 않았으면 None 이다
    rating: Rating | None
    published_at: datetime | None
    updated_at: datetime | None


class PublicListing(BaseModel):
    """
    다른 사용자가 공개된 시나리오를 볼 때의 값. 목록과 상세가 같은 모양이다.

    여기 적힌 칸만 나간다. 초안의 내용, 판의 굳힌 내용, 공개하지 않은 판의 정보는 나가지 않는다.
    """

    scenario_id: uuid.UUID
    # 만든 사람. 인증 서버의 public_id 다. 이름은 인증 서버가 안다
    creator_id: uuid.UUID
    title: str
    tagline: str
    description: str
    genres: list[Genre]
    tags: list[str]
    rating: Rating
    # 공개 중인 판의 번호와 변경 내용
    version: int
    version_note: str
    published_at: datetime


class PublicListingPage(BaseModel):
    """공개 목록의 한 쪽."""

    items: list[PublicListing]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
