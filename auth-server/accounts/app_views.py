# auth-server/accounts/app_views.py

"""
앱(Capacitor 로 감싼 화면)의 토큰 길(#429, docs/product/app-refresh.md).

앱의 WebView 는 페이지의 출처가 우리 사이트와 다른 사이트라 SameSite=Strict 의 refresh 쿠키가 실리지 않는다.
그래서 앱은 refresh 토큰을 응답 본문으로 받아 기기의 안전한 저장소에 두고, 갱신과 로그아웃에 본문으로 보낸다.

    POST /api/v1/auth/app/login/verify      로그인 2단계. 1단계(/login)는 웹과 같다
    POST /api/v1/auth/app/refresh           본문의 refresh 토큰으로 새 토큰 쌍을 받는다
    POST /api/v1/auth/app/logout            본문의 refresh 토큰을 폐기한다
    POST /api/v1/auth/app/password/change   비밀번호를 바꾸고 이 기기의 새 토큰 쌍을 받는다

웹의 길과 다른 점
    - 쿠키를 읽지도 쓰지도 않는다.
    - 브라우저의 요청(Origin 이나 Sec-Fetch-Site 머리말이 붙은 것)은 거절한다. 브라우저는 POST 에 Origin 을 늘 붙인다.
      웹 페이지의 스크립트(XSS 포함)가 이 길로 본문의 refresh 토큰을 받아 가지 못하게 한다.
      앱의 네이티브 쪽(플러그인)이 보내는 요청에는 이 머리말이 붙지 않는다.
    - 앱에 준 refresh 토큰은 이 길로만, 웹에 준 것은 웹의 길로만 갱신된다(tokens.py 의 client).

막지 못하는 것: 우리 앱인지는 가리지 않는다(기기 증명은 나중이다). curl 도 이 길을 부를 수 있지만,
비밀번호와 메일의 코드가 있어야 하므로 웹의 로그인보다 약해지지 않는다.
"""

import contextlib

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api_schema import TOO_MANY_ATTEMPTS, bad_request, coded, detail, unauthenticated
from accounts.models import TokenClient
from accounts.serializers import (
    AppLogoutSerializer,
    AppRefreshTokenSerializer,
    AppTokenResponseSerializer,
    LoginVerifySerializer,
    PasswordChangeSerializer,
)
from accounts.tokens import (
    InvalidRefreshTokenError,
    TokenPair,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
)
from accounts.views import change_password_of, refuse_blocked_network, verify_login

# 브라우저가 보낸 요청에만 붙는 머리말(Django 의 META 이름). 둘 중 하나라도 있으면 브라우저다
BROWSER_HEADERS = ('HTTP_ORIGIN', 'HTTP_SEC_FETCH_SITE')

BROWSER_REFUSED = coded('브라우저에서 온 요청(browser_not_allowed). 앱의 네이티브 쪽만 부른다')


def is_browser_request(request: Request) -> bool:
    """브라우저가 보낸 요청인가. Origin 이나 Sec-Fetch-Site 가 붙었으면 그렇다(값이 "null" 이어도)."""
    return any(name in request.META for name in BROWSER_HEADERS)


def build_browser_refused_response() -> Response:
    """브라우저에서 온 요청의 응답."""
    return Response(
        {'detail': '앱에서만 부를 수 있습니다.', 'code': 'browser_not_allowed'},
        status=status.HTTP_403_FORBIDDEN,
    )


def refuse_browser(request: Request) -> Response | None:
    """브라우저의 요청이면 거절의 응답을, 아니면 None 을 돌려준다."""
    if is_browser_request(request):
        return build_browser_refused_response()
    return None


def build_app_token_response(token_pair: TokenPair) -> Response:
    """토큰 쌍을 앱의 응답으로 바꾼다. 웹의 응답(views.build_token_response)과 같고 refresh 토큰이 본문에 있다."""
    body = AppTokenResponseSerializer(
        {
            'access_token': token_pair.access,
            'token_type': 'Bearer',
            'expires_in': int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
            'consents_pending': list(token_pair.consents_pending),
            'withdrawal_scheduled_at': token_pair.withdrawal_scheduled_at,
            'refresh_token': token_pair.refresh,
            'refresh_expires_in': int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        }
    )
    return Response(body.data, status=status.HTTP_200_OK)


def build_app_session_expired_response() -> Response:
    """refresh 토큰을 쓸 수 없을 때의 응답. 앱은 저장소의 토큰을 지우고 로그인 화면으로 간다."""
    return Response({'detail': '다시 로그인해 주세요.'}, status=status.HTTP_401_UNAUTHORIZED)


class AppLoginVerifyView(APIView):
    """POST /api/v1/auth/app/login/verify"""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='앱의 로그인 2단계: 코드를 맞히면 토큰을 준다. refresh 토큰은 본문이다',
        request=LoginVerifySerializer,
        responses={
            200: AppTokenResponseSerializer,
            400: bad_request('형식이 틀렸거나 코드가 맞지 않거나 만료됐다'),
            401: coded('로그인 티켓을 쓸 수 없다(login_ticket_invalid). 처음부터 다시 한다'),
            403: coded('브라우저에서 온 요청(browser_not_allowed) 또는 막은 IP 다(network_blocked)'),
        },
    )
    def post(self, request: Request) -> Response:
        refused = refuse_browser(request)
        if refused is not None:
            return refused

        verified = verify_login(request)
        if isinstance(verified, Response):
            return verified
        return build_app_token_response(issue_token_pair(verified, TokenClient.APP))


class AppRefreshView(APIView):
    """POST /api/v1/auth/app/refresh"""

    # access 토큰이 만료된 뒤에 부르는 API 다. 본문의 refresh 토큰만 본다
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='앱의 refresh 토큰으로 새 access 토큰을 받는다. refresh 토큰도 새것으로 바뀐다',
        request=AppRefreshTokenSerializer,
        responses={
            200: AppTokenResponseSerializer,
            400: bad_request(),
            401: detail('refresh 토큰을 쓸 수 없다(위조, 만료, 폐기, 웹에 준 토큰). 다시 로그인한다'),
            403: coded('브라우저에서 온 요청(browser_not_allowed) 또는 막은 IP 다(network_blocked)'),
        },
    )
    def post(self, request: Request) -> Response:
        refused = refuse_browser(request)
        if refused is not None:
            return refused

        # 막은 IP 면 새 토큰을 주지 않는다(#638). 웹의 갱신과 같다
        blocked = refuse_blocked_network(request, 'refresh')
        if blocked is not None:
            return blocked

        serializer = AppRefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token_pair = rotate_refresh_token(serializer.validated_data['refresh_token'], TokenClient.APP)
        except InvalidRefreshTokenError:
            # 위조, 만료, 폐기, 다른 곳에 준 토큰을 구분해 알려 주지 않는다
            return build_app_session_expired_response()
        return build_app_token_response(token_pair)


class AppLogoutView(APIView):
    """POST /api/v1/auth/app/logout"""

    # access 토큰이 만료된 상태에서도 로그아웃은 되어야 한다
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='앱의 이 기기에서 로그아웃한다. 본문의 refresh 토큰을 폐기한다',
        request=AppLogoutSerializer,
        responses={
            204: OpenApiResponse(description='로그아웃했다. 토큰이 없었거나 쓸 수 없었어도 같다'),
            400: bad_request(),
            403: BROWSER_REFUSED,
        },
    )
    def post(self, request: Request) -> Response:
        refused = refuse_browser(request)
        if refused is not None:
            return refused

        serializer = AppLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data.get('refresh_token')
        if refresh_token is not None:
            # 이미 쓸 수 없는 토큰이면 로그아웃의 목적은 이미 달성되어 있다
            with contextlib.suppress(InvalidRefreshTokenError):
                revoke_refresh_token(refresh_token, TokenClient.APP)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AppPasswordChangeView(APIView):
    """POST /api/v1/auth/app/password/change"""

    # 로그인한 본인만 바꿀 수 있다. 기본 권한(IsAuthenticated)을 쓴다

    @extend_schema(
        summary='앱에서 비밀번호를 바꾼다. 다른 기기는 로그아웃되고 이 기기는 새 토큰을 받는다(refresh 토큰은 본문)',
        request=PasswordChangeSerializer,
        responses={
            200: AppTokenResponseSerializer,
            400: bad_request('현재 비밀번호가 틀렸거나(current_password) 새 비밀번호가 규칙에 어긋났다(new_password)'),
            401: unauthenticated(),
            403: BROWSER_REFUSED,
            429: TOO_MANY_ATTEMPTS,
        },
    )
    def post(self, request: Request) -> Response:
        refused = refuse_browser(request)
        if refused is not None:
            return refused

        refused = change_password_of(request)
        if refused is not None:
            return refused
        return build_app_token_response(issue_token_pair(request.user, TokenClient.APP))
