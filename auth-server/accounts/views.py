# auth-server/accounts/views.py

"""
accounts 앱의 API 뷰.

뷰는 HTTP 만 다룬다. 요청을 Serializer 로 검증하고, service 를 호출하고,
결과를 응답으로 바꾼다. 규칙과 DB 작업은 여기에 두지 않는다.
"""

import contextlib
import math
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.age import korean_today
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
from accounts.email_codes import InvalidEmailCodeError
from accounts.guardian import (
    GuardianConsentActiveError,
    GuardianEmailIsOwnError,
    GuardianIsMinorError,
    GuardianNotAdultError,
    GuardianNotNeededError,
    GuardianRequestUnavailableError,
    IdentityRequiredError,
    give_guardian_consent,
    guardian_status_of,
    request_guardian_consent,
    revoke_guardian_consent,
)
from accounts.guardian_links import InvalidGuardianLinkError
from accounts.guardian_notices import PaymentNotice, record_payment_notice
from accounts.identity import (
    IdentityAlreadyVerifiedError,
    IdentityInUseError,
    UnderMinAgeError,
    verify_identity,
)
from accounts.identity_providers import IdentityTokenError, IdentityUnavailableError
from accounts.identity_status import identity_status_of
from accounts.jwks import build_jwks
from accounts.login_tickets import InvalidLoginTicketError
from accounts.models import User
from accounts.origin_check import is_allowed_origin, log_refused_origin, read_origin
from accounts.serializers import (
    EmailSerializer,
    GuardianConsentSerializer,
    GuardianNoticeSerializer,
    GuardianRequestSerializer,
    GuardianRevokeSerializer,
    IdentityStatusSerializer,
    IdentityVerifySerializer,
    LoginChallengeSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LoginTicketSerializer,
    LoginVerifySerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    SignupCompleteSerializer,
    SignupSerializer,
    SignupVerifiedSerializer,
    SignupVerifySerializer,
    UserSerializer,
)
from accounts.service_signature import SIGNATURE_HEADER, verify_request
from accounts.services import (
    DuplicateAccountError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidSignupFieldError,
    LoginCodeUnavailableError,
    UnacceptablePasswordError,
    WrongCurrentPasswordError,
    change_password,
    complete_login,
    complete_signup,
    request_password_reset,
    resend_login_code,
    reset_password,
    spend_password_check_time,
    start_login,
    start_signup,
    verify_signup,
)
from accounts.session_revocations import build_revocation_document
from accounts.signup_tickets import InvalidSignupTicketError
from accounts.throttles import (
    LoginIpThrottle,
    PasswordResetIpThrottle,
    SignupIpThrottle,
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
    body = LoginResponseSerializer(
        {
            'access_token': token_pair.access,
            'token_type': 'Bearer',
            'expires_in': int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
        }
    )
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


def build_origin_refused_response() -> Response:
    """
    허용하지 않은 출처에서 온 쿠키 요청의 응답. 쿠키는 지우지 않는다.

    지우면 다른 곳의 페이지가 사용자를 로그아웃시킬 수 있다. 그것이 이 검사로 막으려는 일이다.
    """
    return Response(
        {'detail': '허용하지 않은 곳에서 온 요청입니다.', 'code': 'origin_not_allowed'},
        status=status.HTTP_403_FORBIDDEN,
    )


def refuse_unknown_origin(request: Request) -> Response | None:
    """쿠키를 쓰는 요청의 출처를 본다. 허용하지 않은 출처면 거부 응답을, 허용한 출처면 None 을 돌려준다."""
    origin = read_origin(request)
    if is_allowed_origin(origin):
        return None
    log_refused_origin(origin, request.path)
    return build_origin_refused_response()


def build_login_ticket_invalid_response() -> Response:
    """로그인 티켓을 쓸 수 없을 때의 응답. 위조, 만료, 계정 상태 변경을 구분해 알려 주지 않는다."""
    return Response(
        {'detail': '로그인을 처음부터 다시 해 주세요.', 'code': 'login_ticket_invalid'},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def build_code_unavailable_response(retry_after: timedelta) -> Response:
    """인증 코드를 지금은 보낼 수 없을 때의 응답."""
    return build_retry_later_response(
        '인증 코드를 너무 자주 요청했습니다. 잠시 뒤에 다시 시도해 주세요.', 'login_code_unavailable', retry_after
    )


def build_retry_later_response(detail: str, code: str, retry_after: timedelta) -> Response:
    """
    메일을 지금은 보낼 수 없을 때의 응답(429).

    기다릴 시간을 본문과 Retry-After 머리말에 초 단위로 싣는다. 올림해서, 그 시간 뒤에는 반드시 되게 한다.
    """
    seconds = max(1, math.ceil(retry_after.total_seconds()))
    response = Response(
        {'detail': detail, 'code': code, 'retry_after': seconds},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response['Retry-After'] = str(seconds)
    return response


def build_identity_body(user: User) -> dict:
    """계정의 본인인증 상태를 응답에 싣는 모양으로 바꾼다. 오늘은 한국 날짜다."""
    return IdentityStatusSerializer(identity_status_of(user, korean_today())).data


def build_coded_error_response(detail: str, code: str, status_code: int) -> Response:
    """요청을 거절하는 응답. 화면이 가를 수 있게 오류의 이름(code)을 싣는다."""
    return Response({'detail': detail, 'code': code}, status=status_code)


def build_under_age_response() -> Response:
    """만 14세 미만이라 계정을 막은 뒤의 응답. 이 기기의 refresh 쿠키도 지운다. 세션은 이미 끊겼다."""
    response = build_coded_error_response(
        '만 14세 미만은 이용할 수 없습니다. 계정을 막고 가입할 때 받은 정보를 지웠습니다.',
        'identity_under_age',
        status.HTTP_403_FORBIDDEN,
    )
    clear_refresh_cookie(response)
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
    """POST /api/v1/auth/signup. 가입의 1단계: 이메일로 코드를 보낸다. 다시 보낼 때도 이것이다."""

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

        start_signup(**serializer.validated_data)

        # 새 이메일이든 이미 가입된 이메일이든, 발급 제한에 걸렸든 아니든 같은 응답을 준다.
        # 계정은 아직 없다. 201(만들어짐)이 아니라 202(접수됨)다
        return Response(
            {'detail': '인증 메일을 보냈습니다. 메일에 적힌 코드를 입력해 주세요.'},
            status=status.HTTP_202_ACCEPTED,
        )


class SignupVerifyView(APIView):
    """POST /api/v1/auth/signup/verify. 가입의 2단계: 코드를 확인하고 가입 티켓을 준다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ticket = verify_signup(**serializer.validated_data)
        except InvalidEmailCodeError:
            # 틀림, 만료, 이미 씀, 보낸 코드가 없음(이미 가입된 주소 포함)을 구분해 알려 주지 않는다
            return Response(
                {'detail': '인증 코드가 올바르지 않거나 만료되었습니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = SignupVerifiedSerializer(
            {'detail': '이메일을 확인했습니다. 아이디와 비밀번호를 정해 가입을 마쳐 주세요.', 'signup_ticket': ticket}
        )
        return Response(body.data, status=status.HTTP_200_OK)


class SignupCompleteView(APIView):
    """POST /api/v1/auth/signup/complete. 가입의 3단계: 티켓과 가입 내용으로 계정을 만든다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = SignupCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            complete_signup(**serializer.validated_data)
        except InvalidSignupTicketError:
            return Response(
                {'detail': '가입을 처음부터 다시 해 주세요.', 'code': 'signup_ticket_invalid'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidSignupFieldError as exc:
            # DRF 의 검증 오류와 같은 모양으로 응답한다
            return Response({exc.field: exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        except EmailAlreadyRegisteredError:
            return Response(
                {'detail': '이미 가입을 마친 이메일입니다. 로그인해 주세요.', 'code': 'email_registered'},
                status=status.HTTP_409_CONFLICT,
            )
        except DuplicateAccountError:
            return Response(
                {'detail': '방금 다른 가입이 같은 아이디, 닉네임 또는 이메일을 가져갔습니다. 다시 시도해 주세요.'},
                status=status.HTTP_409_CONFLICT,
            )

        # 이메일은 이미 확인했다. 로그인은 따로 한다(로그인도 이메일 코드를 받는다)
        return Response(
            {'detail': '가입을 마쳤습니다. 로그인해 주세요.'},
            status=status.HTTP_201_CREATED,
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

        # 예약어 아이디면 센다. 한도를 채우면 다음 요청부터 이 IP 가 막힌다. 이 요청은 그대로 진행한다.
        # 그 아이디의 계정이 있으면 세지 않는다(규칙이 넓어지기 전에 만든 계정). 없으면 아래에서 평소처럼 거절된다
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
        # 쿠키를 읽기 전에 본다. 우리 화면에서 온 요청에만 쿠키를 쓴다
        refused = refuse_unknown_origin(request)
        if refused is not None:
            return refused

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
        # 다른 곳의 페이지가 사용자를 로그아웃시키지 못하게 한다
        refused = refuse_unknown_origin(request)
        if refused is not None:
            return refused

        refresh_token = read_refresh_cookie(request)
        if refresh_token is not None:
            # 이미 쓸 수 없는 토큰이면 로그아웃의 목적은 이미 달성되어 있다
            with contextlib.suppress(InvalidRefreshTokenError):
                revoke_refresh_token(refresh_token)

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


class SessionRevocationsView(APIView):
    """GET /api/v1/auth/session-revocations"""

    # 다른 서버가 30초마다 받아 간다(#274). JWKS 처럼 인증 없이 열린다. 사용자는 해시로만 실린다
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        response = Response(build_revocation_document(timezone.now()), status=status.HTTP_200_OK)
        # 중간에서 기억해 두지 않는다. 끊은 세션이 늦게 알려지면 이 목록을 두는 뜻이 줄어든다
        response['Cache-Control'] = 'no-store'
        return response


class IdentityVerifyView(APIView):
    """POST /api/v1/auth/identity/verify. 휴대폰 본인인증(#336)."""

    # 로그인한 본인만 한다. 기본 권한(IsAuthenticated)을 쓴다

    def post(self, request: Request) -> Response:
        serializer = IdentityVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            verify_identity(user=request.user, ip=get_attempt_subject(request), **serializer.validated_data)
        except IdentityAlreadyVerifiedError:
            return build_coded_error_response(
                '이미 본인인증을 마친 계정입니다.', 'identity_already_verified', status.HTTP_409_CONFLICT
            )
        except IdentityTokenError:
            # 위조, 만료, 이미 쓴 것을 구분해 알려 주지 않는다
            return build_coded_error_response(
                '본인인증을 처음부터 다시 해 주세요.', 'identity_token_invalid', status.HTTP_400_BAD_REQUEST
            )
        except IdentityUnavailableError:
            return build_coded_error_response(
                '지금은 본인인증을 받을 수 없습니다.', 'identity_unavailable', status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except IdentityInUseError:
            return build_coded_error_response(
                '다른 계정에서 이미 본인인증을 마친 분입니다. 한 분은 한 계정에서만 인증할 수 있습니다.',
                'identity_in_use',
                status.HTTP_409_CONFLICT,
            )
        except UnderMinAgeError:
            return build_under_age_response()

        # 토큰은 다시 주지 않는다. 화면이 갱신(refresh)을 부르면 adult_content 가 실린 토큰을 받는다.
        # 여기서 새 쌍을 주면 쿠키 속의 옛 refresh 토큰이 폐기되지 않은 채 남는다
        return Response({'identity': build_identity_body(request.user)}, status=status.HTTP_201_CREATED)


def build_guardian_link_invalid_response() -> Response:
    """보호자의 링크를 쓸 수 없을 때의 응답. 위조, 만료, 새 요청으로 바뀐 링크를 구분하지 않는다."""
    return build_coded_error_response(
        '링크를 쓸 수 없습니다. 회원에게 다시 요청해 달라고 해 주세요.',
        'guardian_link_invalid',
        status.HTTP_400_BAD_REQUEST,
    )


class GuardianRequestView(APIView):
    """POST /api/v1/auth/guardian/request. 미성년자가 보호자에게 결제 동의를 부탁한다(#336)."""

    # 로그인한 본인만 한다. 기본 권한(IsAuthenticated)을 쓴다

    def post(self, request: Request) -> Response:
        serializer = GuardianRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            request_guardian_consent(minor=request.user, **serializer.validated_data)
        except IdentityRequiredError:
            return build_coded_error_response(
                '먼저 본인인증을 해 주세요.', 'identity_verification_required', status.HTTP_403_FORBIDDEN
            )
        except GuardianNotNeededError:
            return build_coded_error_response(
                '성년이라 보호자의 동의가 필요 없습니다.', 'guardian_not_needed', status.HTTP_409_CONFLICT
            )
        except GuardianConsentActiveError:
            return build_coded_error_response(
                '보호자가 이미 동의했습니다. 보호자를 바꾸려면 지금의 보호자가 먼저 철회해야 합니다.',
                'guardian_consent_active',
                status.HTTP_409_CONFLICT,
            )
        except GuardianEmailIsOwnError:
            return Response(
                {'guardian_email': ['보호자의 이메일을 적어 주세요. 내 이메일은 쓸 수 없습니다.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except GuardianRequestUnavailableError as exc:
            return build_retry_later_response(
                '보호자에게 너무 자주 요청했습니다. 잠시 뒤에 다시 시도해 주세요.',
                'guardian_request_unavailable',
                exc.retry_after,
            )

        return Response(
            {'detail': '보호자에게 동의 요청 메일을 보냈습니다.', 'guardian_consent': 'requested'},
            status=status.HTTP_202_ACCEPTED,
        )


class GuardianConsentView(APIView):
    """POST /api/v1/auth/guardian/consent. 보호자가 메일의 링크에서 본인인증을 하고 동의한다."""

    # 보호자는 계정이 없다. 링크의 서명과 보호자의 본인인증이 확인이다
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = GuardianConsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            give_guardian_consent(**serializer.validated_data)
        except InvalidGuardianLinkError:
            return build_guardian_link_invalid_response()
        except GuardianNotNeededError:
            return build_coded_error_response(
                '그 회원은 이미 성년이라 동의가 필요 없습니다.', 'guardian_not_needed', status.HTTP_409_CONFLICT
            )
        except IdentityTokenError:
            return build_coded_error_response(
                '본인인증을 처음부터 다시 해 주세요.', 'identity_token_invalid', status.HTTP_400_BAD_REQUEST
            )
        except IdentityUnavailableError:
            return build_coded_error_response(
                '지금은 본인인증을 받을 수 없습니다.', 'identity_unavailable', status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except GuardianNotAdultError:
            return build_coded_error_response(
                '보호자는 성년(만 19세 이상)이어야 합니다.', 'guardian_not_adult', status.HTTP_403_FORBIDDEN
            )
        except GuardianIsMinorError:
            return build_coded_error_response(
                '회원 본인은 보호자가 될 수 없습니다.', 'guardian_is_minor', status.HTTP_409_CONFLICT
            )

        return Response({'detail': '동의를 적었습니다. 확인 메일을 보냈습니다.'}, status=status.HTTP_200_OK)


class GuardianRevokeView(APIView):
    """POST /api/v1/auth/guardian/revoke. 보호자가 메일의 링크로 동의를 철회한다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = GuardianRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            revoked = revoke_guardian_consent(**serializer.validated_data)
        except InvalidGuardianLinkError:
            return build_guardian_link_invalid_response()

        # 이미 철회된 링크를 다시 열어도 같은 결과다. 이번에 철회했는지만 알려 준다
        return Response({'detail': '동의를 철회했습니다.', 'revoked': revoked}, status=status.HTTP_200_OK)


def has_billing_signature(request: Request) -> bool:
    """
    요청이 결제 서버가 서명해 보낸 것인지 본다. 비밀은 BILLING_SECRET 이다(결제 서버의 AUTH_SERVER_SECRET 과 같은 값).

    본문을 읽기 전에 부른다. 서명한 바이트 그대로(request.body)와 주소(경로와 그 뒤의 값)로 확인한다.
    """
    return verify_request(
        secret=settings.BILLING_SECRET,
        header=request.headers.get(SIGNATURE_HEADER, ''),
        method=request.method,
        request_uri=request.get_full_path(),
        body=request.body,
        now=int(time.time()),
    )


class ServiceGuardianNoticeView(APIView):
    """POST /api/v1/auth/service/guardian-notices. 결제 서버가 미성년자의 결제와 청약철회를 알린다(#352)."""

    # 사용자의 토큰이 아니라 결제 서버의 서명으로 확인한다. 프록시는 이 주소를 바깥에 열지 않는다
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        if not has_billing_signature(request):
            return build_coded_error_response(
                '서명이 맞지 않습니다.', 'service_bad_signature', status.HTTP_401_UNAUTHORIZED
            )
        serializer = GuardianNoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = serializer.validated_data

        outcome = record_payment_notice(
            PaymentNotice(
                order_id=fields['order_id'],
                kind=fields['kind'],
                user_public_id=fields['user_id'],
                product_id=fields['product_id'],
                price=fields['price'],
                credits=fields['credits'],
                occurred_at=fields['occurred_at'],
            )
        )
        # queued(메일을 적었다), skipped(알릴 보호자가 없다), duplicate(이미 받았다). 셋 다 결제 서버에는 끝난 일이다
        return Response({'status': outcome}, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /api/v1/auth/me"""

    # permission_classes 를 적지 않는다. 기본값인 IsAuthenticated 가 적용된다

    def get(self, request: Request) -> Response:
        # 인증 클래스가 토큰을 검증하고 request.user 에 사용자를 넣어 준다
        body = {
            **UserSerializer(request.user).data,
            'identity': build_identity_body(request.user),
            'guardian_consent': guardian_status_of(request.user),
        }
        return Response(body, status=status.HTTP_200_OK)
