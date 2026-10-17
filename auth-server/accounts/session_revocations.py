# auth-server/accounts/session_revocations.py

"""
끊긴 세션의 목록. 다른 서버(게임, 게시판, 결제)가 받아 가서, 끊긴 세션의 access 토큰을 만료 전에 거부한다(#274).

다른 서버는 토큰의 서명과 만료만 보고 인증 서버에 묻지 않는다. 그래서 세션을 끊어도(비밀번호 변경, 계정 정지 등)
그 사용자의 access 토큰은 만료(15분)까지 그쪽에서 통했다. 이 목록이 그 틈을 30초 안으로 줄인다.

줄 하나는 "이 사용자의 세션 버전(ver)이 min_ver 보다 작은 토큰은 받지 않는다" 는 뜻이다.
access 토큰의 수명이 지난 줄은 싣지 않는다. 그 전에 발급된 access 토큰은 이미 만료되었다. 그래서 목록은 늘 작다.

사용자는 sub(공개 ID) 그대로가 아니라 SHA-256 으로 싣는다.
목록은 JWKS 처럼 로그인 없이 열린다.
누가 세션을 끊었는지(계정이 정지되었는지)를 밖에서 알 수 없게 한다.
공개 ID 는 무작위 UUID 라 해시에서 거꾸로 찾을 수 없다.
"""

import hashlib
from datetime import datetime, timedelta

from django.conf import settings

from accounts.models import User

# access 토큰의 수명에 더하는 여유. 다른 서버는 만료를 10초 봐주고(시계 차이), 목록은 30초마다 받아 간다
REVOCATION_LEEWAY = timedelta(minutes=1)

# 다른 서버가 목록을 받아 가는 간격(초). 응답에도 실어 알린다. 세션을 끊은 뒤 다른 서버에서 막히기까지 이만큼 걸린다
REFRESH_INTERVAL_SECONDS = 30


def sub_digest(sub: str) -> str:
    """토큰의 sub 를 목록에 싣는 모양(SHA-256 의 16진수 64자)으로 바꾼다. 다른 서버도 같은 식으로 계산한다."""
    return hashlib.sha256(sub.encode()).hexdigest()


def revocation_window() -> timedelta:
    """목록에 싣는 기간. 이보다 먼저 끊은 세션의 access 토큰은 이미 만료되었다."""
    return settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] + REVOCATION_LEEWAY


def recent_revocations(now: datetime) -> list[dict[str, object]]:
    """지금 싣는 끊긴 세션들. 사용자마다 한 줄, 그 사용자의 지금 세션 버전이 min_ver 다."""
    since = now - revocation_window()
    rows = User.objects.filter(sessions_revoked_at__gte=since).values_list('public_id', 'token_version')
    return [{'sub_sha256': sub_digest(str(public_id)), 'min_ver': version} for public_id, version in rows]


def build_revocation_document(now: datetime) -> dict[str, object]:
    """목록 주소가 돌려주는 문서."""
    return {
        'revocations': recent_revocations(now),
        'refresh_interval_seconds': REFRESH_INTERVAL_SECONDS,
    }
