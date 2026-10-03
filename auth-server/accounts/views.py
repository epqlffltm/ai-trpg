# auth-server/accounts/views.py

"""
accounts 앱의 API 뷰.

뷰는 HTTP 만 다룬다. 요청을 Serializer 로 검증하고, service 를 호출하고,
결과를 응답으로 바꾼다. 규칙과 DB 작업은 여기에 두지 않는다.
"""

import math
from datetime import timedelta

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.attempt_policies import (
    block_ip_if_reserved_username,
    clear_login_attempts,
    clear_password_change_attempts,
    count_login_attempt,
    count_password_change_attempt,
    is_login_blocked_ip,
)
from accounts.client_ip import get_attempt_subject
from accounts.cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from accounts.jwks import build_jwks
from accounts.email_codes import InvalidEmailCodeError
from accounts.login_tickets import InvalidLoginTicketError
from accounts.serializers import (
    EmailSerializer,
    LoginChallengeSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LoginTicketSerializer,
    LoginVerifySerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    SignupSerializer,
    SignupVerifySerializer,
    UserSerializer,
)
from accounts.services import (
    DuplicateAccountError,
    EmailNotVerifiedError,
    FieldTakenError,
    InvalidCredentialsError,
    LoginCodeUnavailableError,
    UnacceptablePasswordError,
    WrongCurrentPasswordError,
    change_password,
    complete_login,
    request_password_reset,
    resend_login_code,
    resend_signup_code,
    reset_password,
    spend_password_check_time,
    start_login,
    start_signup,
    verify_signup,
)
from accounts.throttles import (
    LoginIpThrottle,
    PasswordResetIpThrottle,
    SignupIpThrottle,
    SignupResendIpThrottle,
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


def build_login_ticket_invalid_response() -> Response:
    """로그인 티켓을 쓸 수 없을 때의 응답. 위조, 만료, 계정 상태 변경을 구분해 알려 주지 않는다."""
    return Response(
        {'detail': '로그인을 처음부터 다시 해 주세요.', 'code': 'login_ticket_invalid'},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def build_code_unavailable_response(retry_after: timedelta) -> Response:
    """
    인증 코드를 지금은 보낼 수 없을 때의 응답.

    기다릴 시간을 본문과 Retry-After 머리말에 초 단위로 싣는다. 올림해서, 그 시간 뒤에는 반드시 되게 한다.
    """
    seconds = max(1, math.ceil(retry_after.total_seconds()))
    response = Response(
        {
            'detail': '인증 코드를 너무 자주 요청했습니다. 잠시 뒤에 다시 시도해 주세요.',
            'code': 'login_code_unavailable',
            'retry_after': seconds,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response['Retry-After'] = str(seconds)
    return response


def build_invalid_credentials_response() -> Response:
    """
    로그인을 거절하는 응답. 아이디가 없든 비밀번호가 틀리든 같은 응답을 준다.

    로그인이 막힌 IP 에도 이 응답을 준다. 막혔다는 것을 알려 주지 않는다.
    """
    return Response(
        {'detail': '아이디 또는 비밀번호가 올바르지 않습니다.'},
        status=status.HTTP_401_UNAUTHORIZED,
    )


class SignupView(APIView):
    """POST /api/v1/auth/signup"""

    # 기본 권한이 IsAuthenticated 라서, 로그인 없이 호출하는 API 는 직접 열어 줘야 한다
    permission_classes = [AllowAny]
    # 로그인 전에 부르는 API 다. 토큰을 읽지 않는다.
    # 만료된 토큰이 헤더에 남아 있어도 가입과 로그인은 되어야 한다
    authentication_classes = []
    # 가입은 메일을 보낸다. 한 IP 가 낼 수 있는 요청 수를 묶는다
    throttle_classes = [SignupIpThrottle]

    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        # 검증에 실패하면 400 과 필드별 오류 메시지로 응답한다
        serializer.is_valid(raise_exception=True)

        try:
            start_signup(**serializer.validated_data)
        except FieldTakenError as exc:
            # DRF 의 검증 오류와 같은 모양으로 응답한다
            return Response({exc.field: [exc.message]}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateAccountError:
            return Response(
                {'detail': '이미 사용 중인 아이디 또는 닉네임입니다.'},
                status=status.HTTP_409_CONFLICT,
            )

        # 새 이메일이든 이미 가입된 이메일이든 같은 응답을 준다.
        # 계정이 아직 완성되지 않았으므로 201(만들어짐)이 아니라 202(접수됨)다
        return Response(
            {'detail': '인증 메일을 보냈습니다. 메일에 적힌 코드를 입력해 주세요.'},
            status=status.HTTP_202_ACCEPTED,
        )


class SignupVerifyView(APIView):
    """POST /api/v1/auth/signup/verify"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            verify_signup(**serializer.validated_data)
        except InvalidEmailCodeError:
            # 틀림, 만료, 이미 씀, 그런 가입이 없음을 구분해 알려 주지 않는다
            return Response(
                {'detail': '인증 코드가 올바르지 않거나 만료되었습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'detail': '이메일 인증이 끝났습니다. 로그인해 주세요.'},
            status=status.HTTP_200_OK,
        )


class SignupResendView(APIView):
    """POST /api/v1/auth/signup/resend"""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [SignupResendIpThrottle]

    def post(self, request: Request) -> Response:
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resend_signup_code(**serializer.validated_data)

        # 진행 중인 가입이 있든 없든, 발급 제한에 걸렸든 아니든 같은 응답을 준다
        return Response(
            {'detail': '가입을 진행 중인 주소라면 인증 메일을 다시 보냈습니다.'},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """POST /api/v1/auth/login"""

    permission_classes = [AllowAny]
    authentication_classes = []
    # 한 IP 의 로그인 시도 전체를 묶는다. 계정별로 틀린 횟수는 post 안에서 따로 센다
    throttle_classes = [LoginIpThrottle]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 누가 어느 계정에 시도하는지. 횟수를 세는 기준이다
        attempt = {
            'ip': get_attempt_subject(request),
            'username': serializer.validated_data['username'],
        }

        if is_login_blocked_ip(ip=attempt['ip']):
            # 맞는 비밀번호여도 확인하지 않는다. 걸리는 시간만 평소의 거절과 맞춘다
            spend_password_check_time(password=serializer.validated_data['password'])
            return build_invalid_credentials_response()

        # 예약어 아이디면 이 IP 를 막는다. 이 요청은 그대로 진행한다.
        # 예약어인 계정은 없으므로 아래에서 평소처럼 거절된다
        block_ip_if_reserved_username(**attempt)

        # 비밀번호를 확인하기 전에 먼저 센다. 한도를 넘었으면 여기서 TooManyAttemptsError 가 난다.
        # 잡지 않는다. 예외 처리기(exception_handlers.py)가 429 로 바꾼다
        count_login_attempt(**attempt)

        try:
            challenge = start_login(**serializer.validated_data)
        except InvalidCredentialsError:
            # 센 횟수를 그대로 둔다. 그것이 틀린 횟수가 된다
            return build_invalid_credentials_response()
        except EmailNotVerifiedError:
            # 비밀번호가 맞은 뒤에만 도달한다. code 는 프론트가 인증 화면으로 보낼 때 쓴다
            clear_login_attempts(**attempt)
            return Response(
                {'detail': '이메일 인증이 필요합니다.', 'code': 'email_not_verified'},
                status=status.HTTP_403_FORBIDDEN,
            )
        except LoginCodeUnavailableError as exc:
            # 이것도 비밀번호가 맞은 뒤다
            clear_login_attempts(**attempt)
            return build_code_unavailable_response(exc.retry_after)

        clear_login_attempts(**attempt)

        if challenge.code_sent:
            detail = '인증 메일을 보냈습니다. 메일에 적힌 코드를 입력해 주세요.'
        else:
            detail = '조금 전에 보낸 인증 코드를 입력해 주세요.'
        body = LoginChallengeSerializer({'detail': detail, 'login_ticket': challenge.ticket})
        # 로그인이 아직 끝나지 않았으므로 200 이 아니라 202(접수됨)다. 토큰도 쿠키도 주지 않는다
        return Response(body.data, status=status.HTTP_202_ACCEPTED)


class LoginVerifyView(APIView):
    """POST /api/v1/auth/login/verify"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = LoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = complete_login(**serializer.validated_data)
        except InvalidLoginTicketError:
            return build_login_ticket_invalid_response()
        except InvalidEmailCodeError:
            return Response(
                {'detail': '인증 코드가 올바르지 않거나 만료되었습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return build_token_response(issue_token_pair(user))


class LoginResendView(APIView):
    """POST /api/v1/auth/login/resend"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = LoginTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            resend_login_code(**serializer.validated_data)
        except InvalidLoginTicketError:
            return build_login_ticket_invalid_response()
        except LoginCodeUnavailableError as exc:
            return build_code_unavailable_response(exc.retry_after)

        return Response(
            {'detail': '인증 메일을 다시 보냈습니다.'},
            status=status.HTTP_200_OK,
        )


class PasswordChangeView(APIView):
    """POST /api/v1/auth/password/change"""

    # 로그인한 본인만 바꿀 수 있다. 기본 권한(IsAuthenticated)을 쓴다

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 현재 비밀번호를 확인하기 전에 먼저 센다. 한도를 넘었으면 예외 처리기가 429 로 바꾼다
        count_password_change_attempt(user=request.user, ip=get_attempt_subject(request))

        try:
            change_password(user=request.user, **serializer.validated_data)
        except WrongCurrentPasswordError:
            # 센 횟수를 그대로 둔다. 그것이 틀린 횟수가 된다
            return Response(
                {'current_password': ['현재 비밀번호가 올바르지 않습니다.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except UnacceptablePasswordError as exc:
            # 현재 비밀번호는 맞았다. 새 비밀번호가 규칙에 어긋났을 뿐이다
            clear_password_change_attempts(user=request.user)
            return Response({'new_password': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        clear_password_change_attempts(user=request.user)

        # 비밀번호가 바뀌면서 이 기기의 토큰도 무효가 됐다.
        # 새 토큰을 발급해, 다른 기기만 로그아웃되고 이 기기는 로그인이 이어지게 한다
        return build_token_response(issue_token_pair(request.user))


class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password/reset"""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetIpThrottle]

    def post(self, request: Request) -> Response:
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request_password_reset(**serializer.validated_data)

        # 가입된 주소든 아니든, 발급 제한에 걸렸든 아니든 같은 응답을 준다
        return Response(
            {'detail': '가입된 주소라면 비밀번호 재설정 메일을 보냈습니다.'},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password/reset/confirm"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reset_password(**serializer.validated_data)
        except InvalidEmailCodeError:
            # 틀림, 만료, 이미 씀, 그런 계정이 없음을 구분해 알려 주지 않는다
            return Response(
                {'detail': '재설정 링크가 올바르지 않거나 만료되었습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except UnacceptablePasswordError as exc:
            return Response({'new_password': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        # 토큰을 주지 않는다. 새 비밀번호로 로그인하게 한다
        return Response(
            {'detail': '비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.'},
            status=status.HTTP_200_OK,
        )


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
