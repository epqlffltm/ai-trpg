# auth-server/accounts/views.py

"""
accounts 앱의 API 뷰.

뷰는 HTTP 만 다룬다. 요청을 Serializer 로 검증하고, service 를 호출하고,
결과를 응답으로 바꾼다. 규칙과 DB 작업은 여기에 두지 않는다.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from accounts.jwks import build_jwks
from accounts.serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    SignupResponseSerializer,
    SignupSerializer,
    UserSerializer,
)
from accounts.services import (
    DuplicateAccountError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)
from accounts.tokens import (
    InvalidRefreshTokenError,
    TokenPair,
    issue_token_pair,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)

# 다른 서버가 공개키를 캐시해도 되는 시간(초).
# 키를 교체할 때는 이 시간 동안 옛 키와 새 키를 함께 내보내야 한다
JWKS_CACHE_SECONDS = 3600


def build_token_response(token_pair: TokenPair) -> Response:
    """
    토큰 쌍을 응답으로 바꾼다. 로그인과 갱신이 같은 모양으로 응답한다.

    access 토큰은 본문에 싣는다. 다른 서버에도 보내야 하므로 프론트가 직접 다룬다.
    refresh 토큰은 쿠키에 싣는다. 프론트의 스크립트가 읽을 일이 없다.
    """
    body = LoginResponseSerializer({
        'access_token': token_pair.access,
        'token_type': 'Bearer',
        'expires_in': int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
    })
    response = Response(body.data, status=status.HTTP_200_OK)
    set_refresh_cookie(response, token_pair.refresh)
    return response


def build_session_expired_response() -> Response:
    """refresh 토큰이 없거나 쓸 수 없을 때의 응답. 쓸 수 없는 쿠키는 지운다."""
    response = Response(
        {'detail': '다시 로그인해 주세요.'},
        status=status.HTTP_401_UNAUTHORIZED,
    )
    clear_refresh_cookie(response)
    return response


class SignupView(APIView):
    """POST /api/v1/auth/signup"""

    # 기본 권한이 IsAuthenticated 라서, 로그인 없이 호출하는 API 는 직접 열어 줘야 한다
    permission_classes = [AllowAny]
    # 로그인 전에 부르는 API 다. 토큰을 읽지 않는다.
    # 만료된 토큰이 헤더에 남아 있어도 가입과 로그인은 되어야 한다
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        # 검증에 실패하면 400 과 필드별 오류 메시지로 응답한다
        serializer.is_valid(raise_exception=True)

        try:
            user = register_user(**serializer.validated_data)
        except DuplicateAccountError:
            return Response(
                {'detail': '이미 사용 중인 아이디, 이메일 또는 닉네임입니다.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            SignupResponseSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/v1/auth/login"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = authenticate_user(**serializer.validated_data)
        except InvalidCredentialsError:
            # 아이디가 없든 비밀번호가 틀리든 같은 응답을 준다
            return Response(
                {'detail': '아이디 또는 비밀번호가 올바르지 않습니다.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return build_token_response(issue_token_pair(user))


class RefreshView(APIView):
    """POST /api/v1/auth/refresh"""

    # access 토큰이 만료된 뒤에 부르는 API 다. 쿠키의 refresh 토큰만 본다
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        refresh_token = read_refresh_cookie(request)
        if refresh_token is None:
            return build_session_expired_response()

        try:
            token_pair = rotate_refresh_token(refresh_token)
        except InvalidRefreshTokenError:
            # 위조, 만료, 폐기를 구분해 알려 주지 않는다
            return build_session_expired_response()

        return build_token_response(token_pair)


class LogoutView(APIView):
    """POST /api/v1/auth/logout"""

    # access 토큰이 만료된 상태에서도 로그아웃은 되어야 한다
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        refresh_token = read_refresh_cookie(request)
        if refresh_token is not None:
            try:
                revoke_refresh_token(refresh_token)
            except InvalidRefreshTokenError:
                # 이미 쓸 수 없는 토큰이다. 로그아웃의 목적은 이미 달성되어 있다
                pass

        # 토큰이 없었든 쓸 수 없었든 결과는 같다. 쿠키를 지우고 성공으로 응답한다
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class LogoutAllView(APIView):
    """POST /api/v1/auth/logout-all"""

    # 다른 기기까지 끊는 동작이다. 본인 확인이 필요하므로 기본 권한(IsAuthenticated)을 쓴다

    def post(self, request: Request) -> Response:
        revoke_all_sessions(request.user)

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class JwksView(APIView):
    """GET /api/v1/auth/jwks"""

    # 공개키만 나간다. 다른 서버가 인증 없이 가져갈 수 있어야 한다
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        response = Response(build_jwks(), status=status.HTTP_200_OK)
        response['Cache-Control'] = f'public, max-age={JWKS_CACHE_SECONDS}'
        return response


class MeView(APIView):
    """GET /api/v1/auth/me"""

    # permission_classes 를 적지 않는다. 기본값인 IsAuthenticated 가 적용된다

    def get(self, request: Request) -> Response:
        # 인증 클래스가 토큰을 검증하고 request.user 에 사용자를 넣어 준다
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)