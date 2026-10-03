# game-server/app/auth/dependencies.py

"""
요청에서 토큰을 꺼내 검증하고, 누가 보낸 요청인지 알려 주는 의존성.

로그인이 필요한 API 는 함수의 인자에 이것을 적는다.

    async def read_me(user: CurrentUser) -> ...

검증의 결과를 HTTP 응답으로 바꾸는 일도 여기서 한다.
  - 토큰이 없거나 틀렸다 -> 401. 클라이언트는 토큰을 갱신하거나 다시 로그인한다.
  - 키를 구할 수 없어 확인하지 못했다 -> 503. 클라이언트의 잘못이 아니다. 로그아웃시키면 안 된다.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwks import REFETCH_INTERVAL_SECONDS, JwksUnavailableError
from app.auth.tokens import AccessClaims, InvalidTokenError, verify_access_token

# Authorization: Bearer <토큰> 머리말을 읽는다.
# auto_error=False: 머리말이 없을 때의 응답을 FastAPI 에 맡기지 않고 아래에서 직접 정한다
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    """
    토큰이 없거나 받아들일 수 없을 때의 응답.

    이유를 적지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
    WWW-Authenticate 는 401 응답에 붙이게 되어 있는 머리말이다. 어떤 방식으로 인증하는지 알려 준다.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='인증이 필요합니다.',
        headers={'WWW-Authenticate': 'Bearer'},
    )


def verification_unavailable() -> HTTPException:
    """
    토큰이 맞는지 확인할 수 없을 때의 응답.

    Retry-After 는 언제 다시 시도하면 되는지 알려 준다. 키를 다시 가져오는 간격과 같다.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail='지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
        headers={'Retry-After': str(REFETCH_INTERVAL_SECONDS)},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AccessClaims:
    """요청의 토큰을 검증하고, 토큰의 주인을 돌려준다."""
    if credentials is None:
        raise unauthorized()

    try:
        return await verify_access_token(credentials.credentials, request.app.state.jwks, request.app.state.settings)
    except InvalidTokenError as error:
        raise unauthorized() from error
    except JwksUnavailableError as error:
        raise verification_unavailable() from error


# 로그인이 필요한 API 가 인자의 형식으로 쓴다
CurrentUser = Annotated[AccessClaims, Depends(get_current_user)]
