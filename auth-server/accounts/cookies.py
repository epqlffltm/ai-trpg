# auth-server/accounts/cookies.py

"""
refresh 토큰을 쿠키로 주고받는다.

refresh 토큰은 응답 본문에 넣지 않는다. httpOnly 쿠키에 담으면
페이지의 스크립트가 읽을 수 없어, XSS 로는 훔쳐 갈 수 없다.
"""

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response

REFRESH_COOKIE_NAME = 'refresh_token'

# 쿠키를 보낼 경로. 인증 서버의 인증 API 에만 실린다.
# 다른 경로의 요청에는 붙지 않아 노출되는 곳이 줄어든다
REFRESH_COOKIE_PATH = '/api/v1/auth'


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """응답에 refresh 토큰 쿠키를 싣는다."""
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path=REFRESH_COOKIE_PATH,
        # 스크립트가 읽지 못하게 한다
        httponly=True,
        # HTTPS 에서만 보낸다. 로컬 개발(HTTP)에서는 끈다
        secure=settings.REFRESH_COOKIE_SECURE,
        # 다른 사이트에서 시작된 요청에는 쿠키를 싣지 않는다.
        # 쿠키로 인증하는 API 는 CSRF 의 대상이 되는데, 이 설정이 그것을 막는다
        samesite='Strict',
    )


def clear_refresh_cookie(response: Response) -> None:
    """
    브라우저의 refresh 토큰 쿠키를 지운다.

    경로와 SameSite 가 심을 때와 같아야 브라우저가 같은 쿠키로 보고 지운다.
    """
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        samesite='Strict',
    )


def read_refresh_cookie(request: Request) -> str | None:
    """요청에 실려 온 refresh 토큰을 돌려준다. 없으면 None."""
    return request.COOKIES.get(REFRESH_COOKIE_NAME)