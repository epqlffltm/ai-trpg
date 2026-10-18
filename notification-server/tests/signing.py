# notification-server/tests/signing.py

"""
테스트가 알림을 넣는 서버 흉내를 낼 때 쓰는 도구. 그 서버처럼 요청에 서명해 보낸다.
"""

import json
import time

from httpx import AsyncClient, Response

from app.main import API_PREFIX
from app.service_auth.signing import SIGNATURE_HEADER, sign

# 서버마다의 테스트용 서명 비밀. 32자 이상이고 서로 다르다(설정의 규칙)
TEST_SECRETS = {
    'game': 'test-game-secret-0123456789abcdef',
    'billing': 'test-billing-secret-0123456789abcd',
    'board': 'test-board-secret-0123456789abcdef',
}


def put_path(source: str) -> str:
    """그 서버가 알림을 넣는 주소."""
    return f'{API_PREFIX}/service/{source}/notifications'


def encode(body: object) -> bytes:
    """보낼 본문. 넣는 서버처럼 한 번 만든 바이트에 서명하고 그것을 보낸다."""
    return json.dumps(body, ensure_ascii=False).encode()


async def signed_put(
    client: AsyncClient,
    body: object,
    *,
    source: str = 'game',
    secret: str | None = None,
    sent_at: int | None = None,
    signed_as: str | None = None,
) -> Response:
    """
    서명한 요청으로 알림을 넣는다.

    secret 을 주지 않으면 그 서버의 테스트 비밀이다. signed_as 를 주면 그 주소로 서명해서(가로챈 서명) 보낸다.
    """
    path = put_path(source)
    raw = body if isinstance(body, bytes) else encode(body)
    signature = sign(
        secret if secret is not None else TEST_SECRETS[source],
        sent_at if sent_at is not None else int(time.time()),
        'POST',
        signed_as or path,
        raw,
    )
    return await client.post(
        path, content=raw, headers={SIGNATURE_HEADER: signature, 'Content-Type': 'application/json'}
    )
