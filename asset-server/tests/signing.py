# asset-server/tests/signing.py

"""
테스트가 페르소나와 판을 가져가는 서버(chat)와 탈퇴를 알리는 인증 서버의 흉내를 낼 때 쓰는 도구.
그 서버처럼 요청에 서명한다. 가져가는 서버는 사용자의 토큰을 함께 보낸다.
"""

import time

from httpx import AsyncClient, Response
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.main import API_PREFIX

# 서버마다의 테스트용 서명 비밀. 32자 이상이고 서로 다르다(설정의 규칙)
TEST_SECRETS = {
    'chat': 'test-chat-secret-0123456789abcdef',
}
# 인증 서버의 테스트용 서명 비밀(탈퇴 알림)
TEST_AUTH_SECRET = 'test-auth-secret-0123456789abcdef'


def service_path(caller: str, rest: str) -> str:
    """그 서버가 부르는 주소. rest 는 /personas/{id} 처럼 / 로 시작한다."""
    return f'{API_PREFIX}/service/{caller}{rest}'


async def signed_get(
    client: AsyncClient,
    rest: str,
    headers: dict | None = None,
    *,
    caller: str = 'chat',
    secret: str | None = None,
    sent_at: int | None = None,
    signed_as: str | None = None,
) -> Response:
    """
    서명한 GET 을 보낸다. headers 에 사용자의 토큰(Authorization)을 넣는다.

    secret 을 주지 않으면 그 서버의 테스트 비밀이다. signed_as 를 주면 그 주소로 서명해서(가로챈 서명) 보낸다.
    """
    path = service_path(caller, rest)
    signature = sign(
        secret if secret is not None else TEST_SECRETS.get(caller, TEST_SECRETS['chat']),
        sent_at if sent_at is not None else int(time.time()),
        'GET',
        signed_as or path,
        b'',
    )
    return await client.get(path, headers={**(headers or {}), SIGNATURE_HEADER: signature})


def withdrawal_path(public_id: str) -> str:
    """인증 서버가 탈퇴를 알리는 주소."""
    return f'{API_PREFIX}/service/users/{public_id}/withdrawal'


async def signed_withdrawal(
    client: AsyncClient,
    public_id: str,
    body: bytes = b'{"withdrawn_at": "2026-10-28T03:00:00Z"}',
    *,
    secret: str = TEST_AUTH_SECRET,
) -> Response:
    """인증 서버처럼 서명해 탈퇴를 알린다. 한 번 만든 바이트에 서명하고 그것을 보낸다."""
    path = withdrawal_path(public_id)
    signature = sign(secret, int(time.time()), 'POST', path, body)
    return await client.post(
        path, content=body, headers={SIGNATURE_HEADER: signature, 'Content-Type': 'application/json'}
    )
