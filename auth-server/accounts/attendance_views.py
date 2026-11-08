# auth-server/accounts/attendance_views.py

"""
출석과 보물 상자의 주소(결제 서버에서 옮겨 왔다, 2026-11-08 결정). 일은 attendance.py 가 한다.

    GET  /api/v1/auth/attendance          오늘의 출석(로그인)
    POST /api/v1/auth/attendance          오늘의 출석 보상을 받는다(로그인)
    GET  /api/v1/auth/attendance/rewards  하루 양과 보물 상자의 확률(로그인 없음. 누구나 본다)

응답의 모양은 결제 서버의 출석과 같다. 양은 다른 크레딧의 양처럼 글자다("140").
받은 실버는 워커가 결제 서버에 맡겨 몇 초 뒤 지갑에 들어간다. 그래서 받기의 응답에 사라지는 시각(expires_at)이 없다.
누구의 출석인지는 토큰에서만 정한다. 본문을 받지 않는다.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import attendance_rules as rules
from accounts import badge_rules
from accounts.api_schema import coded, unauthenticated
from accounts.attendance import (
    AttendanceAlreadyClaimedError,
    AttendanceVerificationRequiredError,
    Claim,
    Status,
    attendance_status,
    claim_attendance,
    schedule,
)

# 확률을 공개하는 주소의 응답을 브라우저와 프록시가 기억해도 되는 시간(초). 표는 PR 로만 바뀐다
REWARDS_CACHE_SECONDS = 300


class AttendanceStatusSerializer(serializers.Serializer):
    """오늘의 출석."""

    today = serializers.DateField(help_text='오늘의 한국 날짜')
    verified = serializers.BooleanField(help_text='false 면 본인인증 전이다. 받을 수 없다')
    claimed = serializers.BooleanField(help_text='오늘 이미 받았는지')
    cycle_day = serializers.IntegerField(help_text='오늘이 주기의 며칠째인지. 받았으면 받은 날의 값이다')
    cycle_length = serializers.IntegerField(help_text='주기의 날 수')
    silver = serializers.CharField(help_text='오늘의 하루 양(실버, 글자)')
    chest = serializers.BooleanField(help_text='오늘 보물 상자를 여는 날인지')


class ChestSerializer(serializers.Serializer):
    """연 보물 상자."""

    table = serializers.CharField(help_text='연 때의 확률표의 버전')
    outcome = serializers.CharField(help_text='결과의 이름')
    name = serializers.CharField(help_text='화면에 보이는 이름')
    silver = serializers.CharField(help_text='받은 실버(글자). 0 이면 꽝이다')


# 연 보물 상자의 모양. 연 날이 아니면 null 이다. 객체를 바로 적는다.
# 참조(allOf)에 nullable 을 붙이면 OpenAPI 3.0 에서 null 이 통하지 않는다(테스트의 응답 검사가 거절한다)
CHEST_SCHEMA = {
    'type': 'object',
    'nullable': True,
    'description': '연 보물 상자. 연 날이 아니면 null 이다',
    'additionalProperties': False,
    'required': ['table', 'outcome', 'name', 'silver'],
    'properties': {
        'table': {'type': 'string', 'description': '연 때의 확률표의 버전'},
        'outcome': {'type': 'string', 'description': '결과의 이름'},
        'name': {'type': 'string', 'description': '화면에 보이는 이름'},
        'silver': {'type': 'string', 'description': '받은 실버(글자). 0 이면 꽝이다'},
    },
}


@extend_schema_field(CHEST_SCHEMA)
class ChestField(serializers.Field):
    """연 보물 상자의 칸. 값이 None 이면 응답에 null 로 나간다."""

    def to_representation(self, value: dict) -> dict:
        return ChestSerializer(value).data


class EarnedBadgeSerializer(serializers.Serializer):
    """이 출석으로 새로 받은 활동 배지 하나(#193). 받는 법은 마이페이지의 배지 목록(GET /me/badges)에 있다."""

    id = serializers.CharField(help_text='배지의 이름. 바뀌지 않는다')
    name = serializers.CharField(help_text='화면에 보이는 이름')


class AttendanceClaimSerializer(serializers.Serializer):
    """받은 출석 보상. 실버는 몇 초 뒤 지갑에 들어간다."""

    day = serializers.DateField(help_text='출석한 한국 날짜')
    cycle_day = serializers.IntegerField()
    silver = serializers.CharField(help_text='하루 양(실버, 글자)')
    chest = ChestField(allow_null=True)
    badges = EarnedBadgeSerializer(many=True, help_text='이 출석으로 새로 받은 활동 배지. 받은 차례다')


class RewardDaySerializer(serializers.Serializer):
    """주기의 하루."""

    day = serializers.IntegerField()
    silver = serializers.CharField()
    chest = serializers.BooleanField()


class RewardOutcomeSerializer(serializers.Serializer):
    """보물 상자의 결과 하나와 그 확률."""

    outcome = serializers.CharField()
    name = serializers.CharField()
    silver = serializers.CharField()
    chance = serializers.IntegerField(help_text='만분율의 확률(1000 은 10%)')
    percent = serializers.CharField(help_text='같은 값을 사람이 읽는 글자로 쓴 것("10%")')


class RewardChestSerializer(serializers.Serializer):
    """보물 상자의 확률표."""

    table = serializers.CharField()
    scale = serializers.IntegerField(help_text='확률의 단위(10000). 결과의 chance 를 모두 더하면 이 값이다')
    outcomes = RewardOutcomeSerializer(many=True)
    expected_silver = serializers.CharField(help_text='상자 하나의 평균 실버(내림, 글자)')


class RewardsSerializer(serializers.Serializer):
    """공개하는 보상표."""

    cycle = RewardDaySerializer(many=True)
    chest = RewardChestSerializer()


def status_body(current: Status) -> dict:
    """오늘의 출석을 응답의 모양으로."""
    return {
        'today': current.today,
        'verified': current.verified,
        'claimed': current.claimed,
        'cycle_day': current.cycle_day,
        'cycle_length': len(schedule()),
        'silver': str(current.silver),
        'chest': current.chest,
    }


def claim_body(claim: Claim) -> dict:
    """받은 출석 보상을 응답의 모양으로."""
    chest = None
    if claim.chest is not None:
        outcome = claim.chest.outcome
        chest = {'table': claim.chest.table, 'outcome': outcome.id, 'name': outcome.name, 'silver': str(outcome.silver)}
    return {
        'day': claim.day,
        'cycle_day': claim.cycle_day,
        'silver': str(claim.silver),
        'chest': chest,
        'badges': [earned_badge_body(badge_id) for badge_id in claim.badges],
    }


def earned_badge_body(badge_id: str) -> dict:
    """새로 받은 배지 하나를 응답의 모양으로."""
    return {'id': badge_id, 'name': badge_rules.BADGES_BY_ID[badge_id].name}


def rewards_body() -> dict:
    """하루 양과 지금의 확률표를 응답의 모양으로."""
    current = schedule()
    table = rules.CURRENT_CHEST
    cycle = [
        {'day': day, 'silver': str(rules.silver_on(current, day)), 'chest': rules.opens_chest(current, day)}
        for day in range(1, len(current) + 1)
    ]
    outcomes = [
        {
            'outcome': outcome.id,
            'name': outcome.name,
            'silver': str(outcome.silver),
            'chance': outcome.chance,
            'percent': rules.percent_of(outcome.chance),
        }
        for outcome in table.outcomes
    ]
    chest = {
        'table': table.version,
        'scale': rules.CHANCE_SCALE,
        'outcomes': outcomes,
        'expected_silver': str(rules.expected_silver(table)),
    }
    return {'cycle': cycle, 'chest': chest}


def coded_refusal(detail: str, code: str, status_code: int) -> Response:
    """거절의 응답. 화면이 가를 수 있게 오류의 이름(code)을 싣는다. 결제 서버의 출석과 같은 이름이다."""
    return Response({'detail': detail, 'code': code}, status=status_code)


class AttendanceView(APIView):
    """GET, POST /api/v1/auth/attendance. 오늘의 출석과 받기."""

    # 로그인한 본인만. 기본 권한(IsAuthenticated)을 쓴다

    @extend_schema(
        summary='오늘의 출석. 받았는지, 주기의 며칠째인지, 오늘의 하루 양, 상자를 여는 날인지, 본인인증을 마쳤는지',
        responses={200: AttendanceStatusSerializer, 401: unauthenticated()},
    )
    def get(self, request: Request) -> Response:
        body = AttendanceStatusSerializer(status_body(attendance_status(request.user)))
        return Response(body.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='오늘의 출석 보상을 받는다. 주기의 마지막 날이면 보물 상자를 연다. 실버는 몇 초 뒤 지갑에 들어간다',
        request=None,
        responses={
            201: AttendanceClaimSerializer,
            401: unauthenticated(),
            403: coded('본인인증 전이다(attendance.verification_required)'),
            409: coded('오늘 이미 받았다(attendance.already_claimed). 한국 자정에 다시 받는다'),
        },
    )
    def post(self, request: Request) -> Response:
        try:
            claim = claim_attendance(request.user)
        except AttendanceVerificationRequiredError:
            return coded_refusal(
                '출석 보상을 받으려면 먼저 본인인증을 해야 합니다.',
                'attendance.verification_required',
                status.HTTP_403_FORBIDDEN,
            )
        except AttendanceAlreadyClaimedError:
            return coded_refusal(
                '오늘은 이미 출석 보상을 받았습니다. 내일 다시 오세요.',
                'attendance.already_claimed',
                status.HTTP_409_CONFLICT,
            )
        return Response(AttendanceClaimSerializer(claim_body(claim)).data, status=status.HTTP_201_CREATED)


class AttendanceRewardsView(APIView):
    """GET /api/v1/auth/attendance/rewards. 하루 양과 보물 상자의 확률. 로그인 없이 누구나 본다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary='출석의 하루 양과 보물 상자의 확률표. 로그인 없이 누구나 본다',
        responses={200: OpenApiResponse(response=RewardsSerializer, description='보상표')},
    )
    def get(self, request: Request) -> Response:
        response = Response(RewardsSerializer(rewards_body()).data, status=status.HTTP_200_OK)
        response['Cache-Control'] = f'public, max-age={REWARDS_CACHE_SECONDS}'
        return response
