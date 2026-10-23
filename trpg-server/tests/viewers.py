# trpg-server/tests/viewers.py

"""
검증을 마친 토큰의 값(AccessClaims)을 직접 만드는 도구. 서비스를 API 없이 부르는 테스트가 쓴다.

토큰에 서명하고 키 목록을 내주는 가짜 인증 서버는 server-core 의 것이다(server_core.testing.tokens).
"""

import uuid
from datetime import UTC, datetime, timedelta

from server_core.auth.tokens import AccessClaims
from server_core.testing.tokens import ACCESS_TOKEN_SECONDS


def make_viewer(
    user_id: uuid.UUID, seconds: float = ACCESS_TOKEN_SECONDS, *, adult_content: bool = False
) -> AccessClaims:
    """
    검증을 마친 토큰의 값을 직접 만든다.

    seconds 는 지금부터 만료까지의 시간이다. 음수를 주면 이미 만료된 것이 된다.
    adult_content 는 성인용 내용을 볼 수 있는지다. 기본은 볼 수 없음이다(인증 서버의 본인인증 전과 같다).
    """
    expires_at = datetime.now(UTC) + timedelta(seconds=seconds)
    return AccessClaims(user_id=user_id, expires_at=expires_at, adult_content=adult_content)
