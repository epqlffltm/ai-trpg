# auth-server/accounts/badge_views.py

"""
활동 배지(#193)의 주소. 일은 badges.py 가 한다.

    GET /api/v1/auth/me/badges   모든 배지와 내가 받았는지(로그인)

배지는 본인만 본다(2026-11-08 결정). 다른 사람의 배지를 읽는 주소는 없다.
받기 전의 배지도 이름과 받는 법을 함께 보인다. 도전과제라서 무엇을 하면 받는지 알아야 한다.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api_schema import unauthenticated
from accounts.badges import BadgeState, my_badges


class BadgeSerializer(serializers.Serializer):
    """배지 하나와 내가 받았는지."""

    id = serializers.CharField(help_text='배지의 이름. 바뀌지 않는다')
    name = serializers.CharField(help_text='화면에 보이는 이름')
    description = serializers.CharField(help_text='어떻게 받는지')
    earned_at = serializers.DateTimeField(allow_null=True, help_text='받은 시각. 아직이면 null 이다')


class MyBadgesSerializer(serializers.Serializer):
    """내 활동 배지."""

    badges = BadgeSerializer(many=True, help_text='모든 배지. 화면에 보일 차례다')
    earned = serializers.IntegerField(help_text='받은 배지의 수')


def badge_body(state: BadgeState) -> dict:
    """배지 하나를 응답의 모양으로."""
    badge = state.badge
    return {'id': badge.id, 'name': badge.name, 'description': badge.description, 'earned_at': state.earned_at}


def badges_body(states: list[BadgeState]) -> dict:
    """내 배지들을 응답의 모양으로."""
    return {
        'badges': [badge_body(state) for state in states],
        'earned': sum(1 for state in states if state.earned_at is not None),
    }


class MyBadgesView(APIView):
    """GET /api/v1/auth/me/badges. 내 활동 배지."""

    # 로그인한 본인만. 기본 권한(IsAuthenticated)을 쓴다

    @extend_schema(
        summary='내 활동 배지. 모든 배지를 차례대로, 받았으면 받은 시각과 함께',
        responses={200: MyBadgesSerializer, 401: unauthenticated()},
    )
    def get(self, request: Request) -> Response:
        body = MyBadgesSerializer(badges_body(my_badges(request.user)))
        return Response(body.data, status=status.HTTP_200_OK)
