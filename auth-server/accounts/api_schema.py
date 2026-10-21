# auth-server/accounts/api_schema.py

"""
API 목록(OpenAPI, #558)에 적는 요청과 응답의 모양. 뷰(views.py)의 @extend_schema 가 여기 것을 쓴다.

뷰는 손으로 만든 dict 를 돌려주는 APIView 라서 drf-spectacular 가 응답을 스스로 알아내지 못한다.
그래서 응답마다 모양을 여기 적는다. 적은 것이 코드와 어긋나지 않게 두 가지가 지킨다.
  - 목록을 만들 때 경고가 하나라도 있으면 실패한다(manage.py spectacular --fail-on-warn). 적지 않은 뷰가 있으면 경고다
  - 테스트가 받은 응답을 모두 목록과 견준다(config/schema_check.py).
    목록에 없는 상태 코드, 없는 칸, 더 붙은 칸이 틀린 것이다

여기의 Serializer 는 목록을 위한 것이다. 응답을 만드는 데 쓰지 않는다(그것은 serializers.py 다).
오류의 모양은 셋이다.
  - {"detail": 글} 또는 {"detail": 글, "code": 이름}. 화면은 code 로 가른다
  - 시도 제한과 메일을 보낼 수 없는 때(429): {"detail", "code", "retry_after"} 와 Retry-After 머리말
  - 칸마다의 검증 오류(400): {"칸 이름": ["글", ...]}. DRF 의 모양 그대로다
"""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers

from accounts.models import GuardianConsentStatus, GuardianNoticeOutcome
from accounts.serializers import IdentityStatusSerializer, UserSerializer


class SessionVersionJWTScheme(SimpleJWTScheme):
    """
    이 서버의 토큰 인증(accounts/authentication.py)을 목록에 bearer 로 적는다.

    simplejwt 의 것을 물려받은 클래스라 drf-spectacular 가 스스로 알아보지 못한다. 적는 모양은 simplejwt 의 것과 같다.
    이 모듈을 불러오면(views.py 가 부른다) 등록된다.
    """

    target_class = 'accounts.authentication.SessionVersionJWTAuthentication'
    name = 'bearer'


class DetailSerializer(serializers.Serializer):
    """글 하나만 싣는 응답. 성공의 안내도, 이유를 가르지 않는 거절도 이 모양이다."""

    detail = serializers.CharField()


class CodedErrorSerializer(serializers.Serializer):
    """화면이 가를 수 있게 오류의 이름(code)을 싣는 거절."""

    detail = serializers.CharField()
    code = serializers.CharField()


class RetryLaterSerializer(serializers.Serializer):
    """시도가 너무 많거나 메일을 지금은 보낼 수 없을 때(429). retry_after 초 뒤에는 된다. Retry-After 머리말도 같다."""

    detail = serializers.CharField()
    code = serializers.CharField()
    retry_after = serializers.IntegerField(min_value=1)


class AuthErrorSerializer(serializers.Serializer):
    """
    access 토큰이 없거나 받아들일 수 없을 때(401). DRF 와 simplejwt 가 만든다.

    토큰이 틀렸으면 code(token_not_valid)와 messages 가 붙는다. 화면은 이유를 가르지 않고 갱신하거나 다시 로그인한다.
    """

    detail = serializers.CharField()
    code = serializers.CharField(required=False)
    messages = serializers.ListField(child=serializers.DictField(), required=False)


class GuardianRequestedSerializer(serializers.Serializer):
    """보호자에게 동의 요청 메일을 보냈다."""

    detail = serializers.CharField()
    guardian_consent = serializers.ChoiceField(choices=[GuardianConsentStatus.REQUESTED])


class GuardianRevokedSerializer(serializers.Serializer):
    """보호자가 철회했다. revoked 는 이번 요청이 철회했는지다(이미 철회된 링크면 false)."""

    detail = serializers.CharField()
    revoked = serializers.BooleanField()


class GuardianNoticeAnswerSerializer(serializers.Serializer):
    """결제 서버에 주는 답. queued(메일을 적었다), skipped(알릴 보호자가 없다), duplicate(이미 받았다)."""

    status = serializers.ChoiceField(choices=[*GuardianNoticeOutcome.values, 'duplicate'])


class IdentityAnswerSerializer(serializers.Serializer):
    """본인인증을 마친 뒤의 상태."""

    identity = IdentityStatusSerializer()


class MeSerializer(UserSerializer):
    """GET /me 의 응답. 계정 정보에 본인인증, 보호자 동의, 다시 받을 동의, 탈퇴의 상태를 더한다."""

    identity = IdentityStatusSerializer()
    guardian_consent = serializers.ChoiceField(choices=['none', *GuardianConsentStatus.values])
    consents_pending = serializers.ListField(child=serializers.CharField())
    withdrawal_scheduled_at = serializers.DateTimeField(allow_null=True)

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            'identity',
            'guardian_consent',
            'consents_pending',
            'withdrawal_scheduled_at',
        )
        read_only_fields = fields


class WithdrawalStateSerializer(serializers.Serializer):
    """탈퇴의 상태(#603). 요청하면 계정을 비울 시각, 취소하면 null 이다."""

    withdrawal_scheduled_at = serializers.DateTimeField(allow_null=True)


class JwkSerializer(serializers.Serializer):
    """공개키 하나(RFC 7517). 토큰 머리말의 kid 로 고른다."""

    kty = serializers.CharField()
    # 이 키로 할 수 있는 일. 서명의 검증(verify)뿐이다(PyJWT 가 붙인다)
    key_ops = serializers.ListField(child=serializers.CharField())
    n = serializers.CharField()
    e = serializers.CharField()
    kid = serializers.CharField()
    use = serializers.CharField()
    alg = serializers.CharField()


class JwksSerializer(serializers.Serializer):
    """검증할 수 있는 공개키 모두. 서명 키가 맨 앞이다. 키를 바꾸는 동안에는 옛 키도 실린다."""

    keys = JwkSerializer(many=True)


class RevocationSerializer(serializers.Serializer):
    """끊긴 세션 하나. sub 의 SHA-256(16진수)과, 그보다 낮으면 거부할 세션 버전."""

    sub_sha256 = serializers.CharField()
    min_ver = serializers.IntegerField()


class RevocationDocumentSerializer(serializers.Serializer):
    """끊긴 세션의 목록(#274). 받는 서버는 refresh_interval_seconds 마다 다시 받는다."""

    revocations = RevocationSerializer(many=True)
    refresh_interval_seconds = serializers.IntegerField()


# 칸마다의 검증 오류. 값은 글의 목록이다. 안에 칸이 있는 것(consents)은 그 안의 칸마다 다시 나뉜다
FIELD_ERRORS = {
    'type': 'object',
    'description': '칸 이름마다 오류의 글. 칸을 가르지 않는 오류는 non_field_errors 다',
    'additionalProperties': {
        'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'object'}],
    },
}

# 400 의 두 모양. 칸마다의 검증 오류이거나, 칸을 가르지 않는 거절({"detail"} 또는 {"detail", "code"})이다
BAD_REQUEST_BODY = {
    'anyOf': [
        FIELD_ERRORS,
        {
            'type': 'object',
            'required': ['detail'],
            'properties': {'detail': {'type': 'string'}, 'code': {'type': 'string'}},
            'additionalProperties': False,
        },
    ],
}


def bad_request(description: str = '요청을 받을 수 없다') -> OpenApiResponse:
    """400. 칸마다의 검증 오류이거나 이유를 적은 거절이다."""
    return OpenApiResponse(response=BAD_REQUEST_BODY, description=description)


def coded(description: str) -> OpenApiResponse:
    """code 가 붙은 거절."""
    return OpenApiResponse(response=CodedErrorSerializer, description=description)


def detail(description: str) -> OpenApiResponse:
    """글 하나뿐인 응답."""
    return OpenApiResponse(response=DetailSerializer, description=description)


def retry_later(description: str) -> OpenApiResponse:
    """429. 기다릴 시간을 본문과 Retry-After 에 싣는다."""
    return OpenApiResponse(response=RetryLaterSerializer, description=description)


def unauthenticated() -> OpenApiResponse:
    """access 토큰이 없거나 받아들일 수 없다(401)."""
    return OpenApiResponse(response=AuthErrorSerializer, description='access 토큰이 없거나 받아들일 수 없다')


# 시도가 너무 많다(429). 시도 제한(throttle 과 accounts/attempt_limits.py)이 막는다
TOO_MANY_ATTEMPTS = retry_later('시도가 너무 많다(too_many_attempts)')
# 허용하지 않은 출처에서 온 쿠키 요청(403, origin_not_allowed). 쿠키는 지우지 않는다
ORIGIN_REFUSED = coded('허용하지 않은 출처에서 온 쿠키 요청(origin_not_allowed)')


# 상태 확인 둘. Django 의 뷰(config/health.py)라 DRF 의 목록에 저절로 들지 않는다. 다른 서버의 목록과 같은 자리에 둔다
STATUS_BODY = {
    'type': 'object',
    'required': ['status'],
    'properties': {'status': {'type': 'string', 'enum': ['ok', 'unavailable']}},
    'additionalProperties': False,
}
HEALTH_PATHS = {
    '/health': {
        'get': {
            'operationId': 'health',
            'summary': '프로세스가 살아 있다. DB 를 보지 않는다',
            'tags': ['health'],
            'security': [],
            'responses': {
                '200': {'description': '살아 있다', 'content': {'application/json': {'schema': STATUS_BODY}}}
            },
        },
    },
    '/health/ready': {
        'get': {
            'operationId': 'ready',
            'summary': 'DB 에 닿으면 200, 아니면 503',
            'tags': ['health'],
            'security': [],
            'responses': {
                '200': {'description': '요청을 받을 수 있다', 'content': {'application/json': {'schema': STATUS_BODY}}},
                '503': {'description': 'DB 에 닿지 않는다', 'content': {'application/json': {'schema': STATUS_BODY}}},
            },
        },
    },
}


def add_health_paths(result: dict, generator, request, public) -> dict:
    """목록에 상태 확인 둘을 더한다. drf-spectacular 의 후처리(POSTPROCESSING_HOOKS)다."""
    result['paths'] = {**HEALTH_PATHS, **result['paths']}
    return result


def close_schema(schema: dict) -> None:
    """
    객체의 모양에 적지 않은 칸을 받지 않게 한다(additionalProperties: false). 이미 정한 것은 그대로 둔다.

    응답에 칸이 더 붙어도 목록과 맞지 않는 것으로 잡으려는 것이다. 칸을 늘리면 목록도 함께 고친다.
    """
    if schema.get('type') == 'object' and 'properties' in schema:
        schema.setdefault('additionalProperties', False)


def close_objects(result: dict, generator, request, public) -> dict:
    """목록의 모든 이름 있는 모양(components.schemas)을 닫는다. drf-spectacular 의 후처리다."""
    for schema in result.get('components', {}).get('schemas', {}).values():
        close_schema(schema)
    return result
