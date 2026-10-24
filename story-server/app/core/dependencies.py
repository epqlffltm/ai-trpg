# story-server/app/core/dependencies.py

"""
라우터들이 함께 쓰는 의존성. 요청 하나의 DB 세션, 목록의 쪽 나누기, 토큰을 함께 든 사용자다(chat 서버와 같은 모양).
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials
from server_core.auth.dependencies import CurrentUser, bearer_scheme, unauthorized
from server_core.auth.tokens import AccessClaims
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

# 요청 하나가 쓰는 DB 세션
Session = Annotated[AsyncSession, Depends(get_session)]

# 목록의 한 쪽에 싣는 개수. 상한을 둔다. 한 번에 전부 달라는 요청으로 서버가 느려지지 않게 한다(chat 서버와 같다)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class PageParams:
    """목록을 어디서부터 몇 개 달라는 요청. 주소의 ?limit=..&offset=.. 에서 읽는다."""

    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    offset: Annotated[int, Query(ge=0)] = 0


# 목록 API 가 인자의 형식으로 쓴다
Paging = Annotated[PageParams, Depends()]


@dataclass(frozen=True)
class Viewer:
    """
    토큰의 주인과 그 토큰. asset 서버를 부를 때 토큰을 그대로 넘긴다("누구를 위해 가져가나").

    토큰은 이 요청 안에서만 쓰고 저장하지 않는다. 로그와 오류에 싣지 않는다.
    """

    claims: AccessClaims
    token: str


async def get_viewer(
    user: CurrentUser, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
) -> Viewer:
    """검증한 토큰의 주인과 그 토큰. CurrentUser 가 먼저 검증하므로 여기의 토큰은 늘 있다(없으면 401)."""
    if credentials is None:
        raise unauthorized()
    return Viewer(claims=user, token=credentials.credentials)


# asset 서버를 부르는 API 와 세션 API 가 인자의 형식으로 쓴다
CurrentViewer = Annotated[Viewer, Depends(get_viewer)]
