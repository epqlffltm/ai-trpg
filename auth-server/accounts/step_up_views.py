# auth-server/accounts/step_up_views.py

"""
민감한 작업 앞의 본인 확인의 주소(F5). 일은 step_up.py 가 한다.

    GET  /api/v1/auth/me/step-up               이 세션의 확인 창(로그인)
    POST /api/v1/auth/me/step-up               메일 코드로 확인하고 이 세션의 창을 연다(로그인)
    POST /api/v1/auth/me/step-up/code          확인 코드를 메일로 보낸다(로그인)
    PUT  /api/v1/auth/me/step-up/setting       본인 확인을 켜거나 끈다. 끄는 것은 창이 열린 동안만(로그인)
    POST /api/v1/auth/service/step-up/check    결제 서버가 민감한 작업 앞에서 묻는다. 열려 있으면 늘린다(서버끼리)

세션은 access 토큰의 sid 다. 결제 서버는 받은 access 토큰의 sub 와 sid 를 그대로 보낸다.
sid 가 없는 옛 토큰이면 화면이 갱신(refresh)한 뒤 다시 하면 된다(step_up_session_unknown).
"""

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api_schema import bad_request, coded, retry_later, unauthenticated
from accounts.email_codes import InvalidEmailCodeError
from accounts.models import User
from accounts.services import StepUpCodeUnavailableError, send_step_up_code
from accounts.step_up import (
    StepUpRequiredError,
    StepUpSessionUnknownError,
    StepUpState,
    WindowStatus,
    check_step_up,
    require_session,
    set_step_up_enabled,
    verify_step_up,
    window_status,
)
from accounts.tokens import SESSION_CLAIM
from accounts.views import build_coded_error_response, build_retry_later_response, has_billing_signature


class StepUpStatusSerializer(serializers.Serializer):
    """이 세션의 확인 창."""

    enabled = serializers.BooleanField(help_text='false 면 본인 확인을 껐다. 청약철회는 화면에서 하지 못한다')
    open = serializers.BooleanField(help_text='창이 열려 있는지. 열려 있으면 민감한 작업에 다시 묻지 않는다')
    expires_at = serializers.DateTimeField(allow_null=True, help_text='창이 닫히는 시각. 닫혀 있으면 null')


class StepUpVerifySerializer(serializers.Serializer):
    """메일로 받은 확인 코드."""

    code = serializers.RegexField(r'^\d{6}$', help_text='메일로 받은 6자리 숫자')


class StepUpCodeSentSerializer(serializers.Serializer):
    """확인 코드를 보낸 결과."""

    detail = serializers.CharField()
    sent = serializers.BooleanField(help_text='false 면 앞서 보낸 코드가 아직 쓸 수 있어 새로 보내지 않았다')


class StepUpSettingSerializer(serializers.Serializer):
    """본인 확인을 켜고 끄기."""

    enabled = serializers.BooleanField(help_text='false 면 끈다. 끄는 것은 창이 열린 동안에만 된다')


class StepUpCheckSerializer(serializers.Serializer):
    """결제 서버가 묻는 세션. 받은 access 토큰의 sub 와 sid 다."""

    user_id = serializers.UUIDField(help_text='사용자의 공개 ID(토큰의 sub)')
    session_id = serializers.CharField(max_length=64, help_text='세션의 이름(토큰의 sid)')


class StepUpCheckAnswerSerializer(serializers.Serializer):
    """창의 상태."""

    state = serializers.ChoiceField(choices=[state.value for state in StepUpState])
    expires_at = serializers.DateTimeField(allow_null=True, help_text='open 이면 늘린 뒤의 닫히는 시각')


SESSION_UNKNOWN = coded('토큰에 세션이 없다(step_up_session_unknown). 갱신한 뒤 다시 한다')


def session_of(request: Request) -> str:
    """요청의 access 토큰에 실린 세션 이름. 없으면 StepUpSessionUnknownError."""
    token = request.auth
    return require_session(token.get(SESSION_CLAIM) if token is not None else None)


def session_unknown_response() -> Response:
    return build_coded_error_response(
        '이 기기의 로그인 정보가 오래되었습니다. 새로 고친 뒤 다시 해 주세요.',
        'step_up_session_unknown',
        status.HTTP_409_CONFLICT,
    )


def status_response(window: WindowStatus) -> Response:
    body = {'enabled': window.enabled, 'open': window.open, 'expires_at': window.expires_at}
    return Response(StepUpStatusSerializer(body).data, status=status.HTTP_200_OK)


class MyStepUpView(APIView):
    """GET, POST /api/v1/auth/me/step-up. 이 세션의 확인 창을 보고, 메일 코드로 연다."""

    @extend_schema(
        summary='이 세션의 본인 확인 창. 켜져 있는지, 열려 있는지, 닫히는 시각',
        responses={200: StepUpStatusSerializer, 401: unauthenticated(), 409: SESSION_UNKNOWN},
    )
    def get(self, request: Request) -> Response:
        try:
            session_id = session_of(request)
        except StepUpSessionUnknownError:
            return session_unknown_response()
        return status_response(window_status(request.user, session_id, timezone.now()))

    @extend_schema(
        summary='메일로 받은 코드로 본인을 확인하고 이 세션의 창을 연다(10분)',
        request=StepUpVerifySerializer,
        responses={
            200: StepUpStatusSerializer,
            400: coded('코드가 틀렸거나 만료됐다(step_up_code_invalid)'),
            401: unauthenticated(),
            409: SESSION_UNKNOWN,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = StepUpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        try:
            session_id = session_of(request)
            verify_step_up(request.user, session_id, serializer.validated_data['code'], now)
        except StepUpSessionUnknownError:
            return session_unknown_response()
        except InvalidEmailCodeError:
            # 틀림, 만료, 이미 씀, 보낸 코드가 없음을 구분해 알려 주지 않는다
            return build_coded_error_response(
                '인증 코드가 올바르지 않거나 만료되었습니다.', 'step_up_code_invalid', status.HTTP_400_BAD_REQUEST
            )
        return status_response(window_status(request.user, session_id, now))


class MyStepUpCodeView(APIView):
    """POST /api/v1/auth/me/step-up/code. 확인 코드를 메일로 보낸다."""

    @extend_schema(
        summary='본인 확인 코드를 가입한 메일로 보낸다',
        request=None,
        responses={
            200: StepUpCodeSentSerializer,
            401: unauthenticated(),
            429: retry_later('코드를 너무 자주 요청했다(step_up_code_unavailable)'),
        },
    )
    def post(self, request: Request) -> Response:
        try:
            sent = send_step_up_code(request.user)
        except StepUpCodeUnavailableError as exc:
            return build_retry_later_response(
                '인증 코드를 너무 자주 요청했습니다. 잠시 뒤에 다시 시도해 주세요.',
                'step_up_code_unavailable',
                exc.retry_after,
            )
        detail = '인증 메일을 보냈습니다.' if sent else '조금 전에 보낸 인증 메일의 코드를 넣어 주세요.'
        return Response({'detail': detail, 'sent': sent}, status=status.HTTP_200_OK)


class MyStepUpSettingView(APIView):
    """PUT /api/v1/auth/me/step-up/setting. 민감한 작업의 본인 확인을 켜거나 끈다."""

    @extend_schema(
        summary='민감한 작업의 본인 확인을 켜거나 끈다. 끄는 것은 이 세션의 창이 열린 동안에만 된다',
        request=StepUpSettingSerializer,
        responses={
            200: StepUpStatusSerializer,
            400: bad_request(),
            401: unauthenticated(),
            403: coded('끄려면 먼저 본인 확인을 해야 한다(step_up_required)'),
            409: SESSION_UNKNOWN,
        },
    )
    def put(self, request: Request) -> Response:
        serializer = StepUpSettingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        try:
            session_id = session_of(request)
            set_step_up_enabled(request.user, session_id, serializer.validated_data['enabled'], now)
        except StepUpSessionUnknownError:
            return session_unknown_response()
        except StepUpRequiredError:
            return build_coded_error_response(
                '본인 확인을 끄려면 먼저 본인 확인을 해 주세요.', 'step_up_required', status.HTTP_403_FORBIDDEN
            )
        return status_response(window_status(request.user, session_id, now))


class ServiceStepUpCheckView(APIView):
    """POST /api/v1/auth/service/step-up/check. 결제 서버가 민감한 작업 앞에서 그 세션의 창을 묻는다."""

    # 사용자의 토큰이 아니라 결제 서버의 서명으로 확인한다. 프록시는 이 주소를 바깥에 열지 않는다
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='결제 서버가 민감한 작업 앞에서 그 세션의 본인 확인 창을 묻는다. 열려 있으면 늘린다(서버끼리)',
        request=StepUpCheckSerializer,
        responses={
            200: StepUpCheckAnswerSerializer,
            400: bad_request(),
            401: coded('결제 서버의 서명이 맞지 않다(service_bad_signature)'),
            404: coded('그런 사용자가 없다(service_user_unknown)'),
        },
    )
    def post(self, request: Request) -> Response:
        if not has_billing_signature(request):
            return build_coded_error_response(
                '서명이 맞지 않습니다.', 'service_bad_signature', status.HTTP_401_UNAUTHORIZED
            )
        serializer = StepUpCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            public_id=serializer.validated_data['user_id'], is_active=True, withdrawn_at__isnull=True
        ).first()
        if user is None:
            return build_coded_error_response(
                '그런 사용자가 없습니다.', 'service_user_unknown', status.HTTP_404_NOT_FOUND
            )
        state, expires_at = check_step_up(user, serializer.validated_data['session_id'], timezone.now())
        return Response({'state': state.value, 'expires_at': expires_at}, status=status.HTTP_200_OK)
