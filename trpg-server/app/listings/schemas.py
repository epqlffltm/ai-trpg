# trpg-server/app/listings/schemas.py

"""
공개 정보 API 가 받는 입력과 내보내는 응답의 모양.

응답이 둘이다. 제작자가 자기 것을 볼 때(ListingDetail)와, 다른 사용자가 공개된 것을 볼 때(PublicListing)다.
어느 쪽에도 판의 굳힌 내용(GM 전용 글이 들어 있다)은 싣지 않는다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import CharacterMode, Rating
from app.assets.scenarios.schemas import RecommendedPlayers
from app.engine.ruleset import Ability
from app.engine.sheet import Sheet
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
    # 제작자가 추천하는 인원. 강제하지 않는다
    recommended_players: RecommendedPlayers
    # 공개 중인 판의 번호와 변경 내용
    version: int
    version_note: str
    published_at: datetime


class ListingPregen(BaseModel):
    """공개된 판의 프리젠 하나. 테이블을 만들기 전에 고를 거리를 보는 값이다. 함께 받는 소지품은 싣지 않는다."""

    name: str
    description: str
    # 이 프리젠을 고르면 받는 숫자. 능력치의 이름은 PublicListingDetail.abilities 에서 찾는다
    sheet: Sheet


class PublicListingDetail(PublicListing):
    """
    공개된 시나리오 하나를 볼 때의 값(#428). 목록의 칸에, 테이블을 만들기 전에 고를 것들이 더 있다.

    테이블을 만들 때(POST /tables) 스타팅의 순번(opening_index), 캐릭터 방식(character_modes), 서술 모델을 고른다.
    남의 시나리오는 판을 읽을 수 없어서 고를 거리를 볼 길이 없었다. 공개 중인 판의 것이다.
    목록(PublicListingPage)에는 싣지 않는다. 스타팅은 다섯 개까지 하나에 2,000 자라 목록에 싣기에는 크다.
    GM 전용 글(진행 지침, GM 메모)과 판의 나머지(로어북, NPC, 몬스터, 퀘스트)는 싣지 않는다.
    """

    # 스타팅들. 테이블을 만들 때 이 중 하나를 순번(0 부터)으로 고른다
    openings: list[str]
    # 허용하는 캐릭터 방식. 테이블을 만들 때 이 안에서 좁힌다
    character_modes: list[CharacterMode]
    pregens: list[ListingPregen]
    # 규칙의 능력치(이름표와 이름). 프리젠의 숫자를 읽는 데 쓴다
    abilities: list[Ability]
    # 제작자가 추천한 서술 모델(이름표). 지금의 값이다(판에 굳히지 않는다). 정하지 않았으면 null 이다.
    # 지금 팔지 않는 모델일 수 있다. 화면은 GET /tables/narration-models 에서 찾는다.
    # 없으면 테이블을 만들 때 같은 회사의 대신 쓸 모델로 정해진다(app/tables/model_choice.py)
    recommended_narration_model: str | None


class PublicListingPage(BaseModel):
    """공개 목록의 한 쪽."""

    items: list[PublicListing]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
