# trpg-server/app/listings/exclusions.py

"""
보는 사람이 막은 제작자와 태그(#988). 공개 목록, 검색, 랭킹, 배너에서 그것의 작품을 뺀다.

막은 목록은 인증 서버에 있다. 이 서버는 인증 서버를 부르지 않는다(공용 코드 규칙의 원칙 2).
화면이 읽어 목록의 주소에 싣는다. 성인 작품 숨김(#986)과 같은 길이다. 소개 하나를 여는 주소에는 싣지 않는다.

    ?exclude_creators=<공개 ID>,<공개 ID>&exclude_tag=<태그>&exclude_tag=<태그>

  - 제작자는 쉼표로 잇는다. UUID 에는 쉼표가 없고, 이름을 되풀이하지 않아 주소가 짧다
  - 태그는 이름을 되풀이한다. 태그에는 쉼표가 들어갈 수 있다
  - 상한은 인증 서버의 것과 같다(제작자 MAX_EXCLUDED_CREATORS, 태그 MAX_EXCLUDED_TAGS, 2026-11-04 유저 결정).
    가장 길면 주소가 9KB 쯤이다(한글 태그는 한 글자가 9바이트). 프록시가 받는 요청의 줄을 16KB 로 둔다
  - 넘거나 모양이 틀리면 422 다. 화면의 잘못이다
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Query
from pydantic import AfterValidator, StringConstraints

from app.listings.models import TAG_MAX_LENGTH

MAX_EXCLUDED_CREATORS = 100
MAX_EXCLUDED_TAGS = 30
# UUID 36자와 쉼표
CREATORS_MAX_LENGTH = MAX_EXCLUDED_CREATORS * 37


@dataclass(frozen=True)
class Exclusions:
    """뺄 제작자(공개 ID)와 태그. 비어 있으면 빼지 않는다."""

    creators: tuple[uuid.UUID, ...] = ()
    tags: tuple[str, ...] = ()


def parse_creators(value: str | None) -> tuple[uuid.UUID, ...]:
    """쉼표로 이은 공개 ID 들. 빈 조각은 버리고 겹친 것은 하나로 본다. UUID 가 아니거나 너무 많으면 ValueError."""
    if value is None:
        return ()
    ids = tuple(dict.fromkeys(uuid.UUID(part.strip()) for part in value.split(',') if part.strip()))
    if len(ids) > MAX_EXCLUDED_CREATORS:
        raise ValueError(f'제작자는 {MAX_EXCLUDED_CREATORS}명까지 뺄 수 있다')
    return ids


ExcludedCreators = Annotated[str | None, Query(max_length=CREATORS_MAX_LENGTH)]
ExcludedTag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TAG_MAX_LENGTH)]
ExcludedTags = Annotated[list[ExcludedTag], Query(max_length=MAX_EXCLUDED_TAGS)]


def to_exclusions(
    exclude_creators: Annotated[ExcludedCreators, AfterValidator(parse_creators)] = None,
    exclude_tag: ExcludedTags = [],  # noqa: B006  FastAPI 가 요청마다 새 목록을 만든다
) -> Exclusions:
    """주소의 뺄 값을 하나로 묶는다."""
    # AfterValidator(parse_creators) 가 주소의 글을 공개 ID 의 묶음으로 바꿔 넘긴다. 타입은 받은 글의 모양으로 적혀 있다
    creators = cast(tuple[uuid.UUID, ...], exclude_creators or ())
    return Exclusions(creators=creators, tags=tuple(dict.fromkeys(exclude_tag)))


ExclusionsParam = Annotated[Exclusions, Depends(to_exclusions)]
