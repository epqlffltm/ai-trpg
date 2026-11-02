# asset-server/app/core/dependencies.py

"""
라우터들이 함께 쓰는 의존성. 요청 하나의 DB 세션, 앱의 설정, 목록의 쪽 나누기다.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.search import SEARCH_MAX_LENGTH, SEARCH_PATTERN, SearchTerms, parse_search

# 요청 하나가 쓰는 DB 세션
Session = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    """앱의 설정. 앱을 만들 때 붙여 둔 것이다(테스트가 바꾼 설정도 이것이다)."""
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


# 목록의 한 쪽에 싣는 개수. 상한을 둔다. 한 번에 전부 달라는 요청으로 서버가 느려지지 않게 한다(게임 서버와 같다)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class PageParams:
    """목록을 어디서부터 몇 개 달라는 요청. 주소의 ?limit=..&offset=.. 에서 읽는다."""

    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    offset: Annotated[int, Query(ge=0)] = 0


# 목록 API 가 인자의 형식으로 쓴다
Paging = Annotated[PageParams, Depends()]


def get_search(
    q: Annotated[str | None, Query(max_length=SEARCH_MAX_LENGTH, pattern=SEARCH_PATTERN)] = None,
) -> SearchTerms | None:
    """
    공개 목록의 검색어(#984). 주소의 ?q=.. 에서 읽는다. 비워 두면 거르지 않는다(None).

    "#"로 시작하면 태그, 아니면 이름에서 찾는다(app/search.py). 공백뿐이거나 "#" 하나뿐이면 422 다.
    """
    return parse_search(q) if q is not None else None


# 공개 목록 API 가 인자의 형식으로 쓴다
Search = Annotated[SearchTerms | None, Depends(get_search)]
