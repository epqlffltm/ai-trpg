# asset-server/app/exclusions.py

"""
보는 사람이 막은 제작자와 태그(#988). 공개 목록, 검색, 랭킹, 배너에서 그것의 캐릭터와 세계관을 뺀다.

막은 목록은 인증 서버에 있다. 이 서버는 인증 서버를 부르지 않는다(공용 코드 규칙의 원칙 2).
화면이 읽어 목록의 주소에 싣는다. 성인 작품 숨김(#986, app/preferences.py)과 같은 길이다.
시나리오의 공개 목록(trpg-server 의 app/listings/exclusions.py)도 같은 규칙이다.

    ?exclude_creators=<공개 ID>,<공개 ID>&exclude_tag=<태그>&exclude_tag=<태그>

  - 제작자는 쉼표로 잇는다(UUID 에는 쉼표가 없고 주소가 짧다). 태그는 이름을 되풀이한다(태그에는 쉼표가 들어갈 수 있다)
  - 제작자 MAX_EXCLUDED_CREATORS 명, 태그 MAX_EXCLUDED_TAGS 개까지다(2026-11-04 유저 결정). 넘거나 모양이 틀리면 422
  - 태그는 마지막 판에 붙은 것을 본다. 하나라도 겹치면 뺀다
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query
from pydantic import AfterValidator, StringConstraints
from sqlalchemy import ColumnElement, and_, true
from sqlalchemy.dialects.postgresql import array

from app.characters.models import CHARACTER_TAG_MAX_LENGTH

MAX_EXCLUDED_CREATORS = 100
MAX_EXCLUDED_TAGS = 30
# UUID 36자와 쉼표
CREATORS_MAX_LENGTH = MAX_EXCLUDED_CREATORS * 37


@dataclass(frozen=True)
class Exclusions:
    """뺄 제작자(공개 ID)와 태그. 비어 있으면 빼지 않는다."""

    creators: tuple[uuid.UUID, ...] = ()
    tags: tuple[str, ...] = ()


# 빼지 않는다. 기본값으로 쓴다
NO_EXCLUSIONS = Exclusions()


def parse_creators(value: str | None) -> tuple[uuid.UUID, ...]:
    """쉼표로 이은 공개 ID 들. 빈 조각은 버리고 겹친 것은 하나로 본다. UUID 가 아니거나 너무 많으면 ValueError."""
    if value is None:
        return ()
    ids = tuple(dict.fromkeys(uuid.UUID(part.strip()) for part in value.split(',') if part.strip()))
    if len(ids) > MAX_EXCLUDED_CREATORS:
        raise ValueError(f'제작자는 {MAX_EXCLUDED_CREATORS}명까지 뺄 수 있다')
    return ids


ExcludedCreators = Annotated[str | None, Query(max_length=CREATORS_MAX_LENGTH), AfterValidator(parse_creators)]
ExcludedTag = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CHARACTER_TAG_MAX_LENGTH)
]
ExcludedTags = Annotated[list[ExcludedTag], Query(max_length=MAX_EXCLUDED_TAGS)]


def build_exclusions(creators: Any, tags: list[str]) -> Exclusions:
    """주소에서 읽은 값을 묶는다. creators 는 parse_creators 의 결과(없으면 None)다. 겹친 태그는 하나로 본다."""
    return Exclusions(creators=creators or (), tags=tuple(dict.fromkeys(tags)))


def not_excluded(excluded: Exclusions, owner_id: Any, document: Any) -> ColumnElement[bool]:
    """
    막은 제작자의 것과 막은 태그가 하나라도 붙은 것을 빼는 조건. 뺄 것이 없으면 참이다.

    owner_id 는 작품의 주인, document 는 마지막 판의 문서다.
    """
    conditions = []
    if excluded.creators:
        conditions.append(owner_id.not_in(excluded.creators))
    if excluded.tags:
        conditions.append(~document['tags'].has_any(array(list(excluded.tags))))
    return and_(*conditions) if conditions else true()
