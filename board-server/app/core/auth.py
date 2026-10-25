# board-server/app/core/auth.py

"""
로그인이 필요한 API 의 사람(Member). 토큰의 검증은 공용 코드가 한다(server_core.auth.dependencies.CurrentUser).

  - 로그인 없이 읽는 API(게시판, 글, 댓글, 검색)는 이것을 쓰지 않는다. 토큰을 보내도 보지 않는다
  - 운영자인지는 토큰의 roles 로 안다(인증 서버의 operators 그룹). 게시판 서버에 운영자 표가 없다
  - 토큰의 닉네임을 그 사람의 닉네임으로 적는다(app/authors/service.py). 글과 댓글의 응답에 실을 이름이다.
    적을 수 없는 닉네임이면 적지 않고 토큰은 받는다
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from server_core.auth.dependencies import CurrentUser, bearer_scheme

from app.authors import service as authors
from app.core.dependencies import Session

# 토큰에서 닉네임이 실린 칸. 인증 서버의 accounts/tokens.py 와 같다
NICKNAME_CLAIM = 'nickname'


@dataclass(frozen=True)
class Actor:
    """요청을 보낸 사람. 글쓴이와 운영자를 가를 때 쓴다."""

    user_id: uuid.UUID
    is_operator: bool
    nickname: str | None = None


def nickname_in(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """
    토큰의 닉네임. 받을 수 없는 모양이면 None 이다.

    공용 코드가 서명과 내용을 이미 확인한 토큰이다. 여기서는 칸 하나를 읽기만 한다.
    """
    if credentials is None:
        return None
    claims = jwt.decode(credentials.credentials, options={'verify_signature': False})
    return authors.read_nickname(claims.get(NICKNAME_CLAIM))


async def get_member(
    request: Request,
    user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Session,
) -> Actor:
    """토큰을 검증하고 닉네임을 적은 뒤 요청을 보낸 사람을 돌려준다. 토큰이 없거나 틀리면 401 이다."""
    nickname = nickname_in(credentials)
    if nickname is not None:
        await authors.remember(session, request.app.state.recent_nicknames, user.user_id, nickname)
    return Actor(user_id=user.user_id, is_operator=user.is_operator, nickname=nickname)


# 로그인이 필요한 API 의 인자
Member = Annotated[Actor, Depends(get_member)]


# 운영자만 부르는 API 의 표시(openapi_extra). API 목록의 x-audience 가 operator 가 된다(tools/export_openapi.py).
# 주소에 /admin/ 이 없어 도구가 주소로 알 수 없다. 표시는 목록에만 쓰인다. 운영자만 부르게 막는 것은 서비스가 한다
FOR_OPERATORS = {'x-audience': 'operator'}
