# game-server/tests/test_me.py

"""
토큰으로 보호되는 API 를 검증한다. 검증의 결과가 올바른 HTTP 응답으로 바뀌는가.

토큰을 받고 거부하는 규칙 자체는 test_tokens.py 가 검증한다. 여기서는 API 까지 이어졌는지를 본다.
"""

import time

from fastapi import status
from httpx import AsyncClient

from app.auth.jwks import REFETCH_INTERVAL_SECONDS
from app.main import API_PREFIX
from tests.signing import TEST_USER_ID, FakeAuthServer, SigningKey, make_access_claims, make_token

ME_URL = f'{API_PREFIX}/me'


def bearer(token: str) -> dict[str, str]:
    """토큰을 요청의 머리말에 싣는다."""
    return {'Authorization': f'Bearer {token}'}


async def test_returns_the_owner_of_the_token(client: AsyncClient, signing_key: SigningKey):
    token = make_token(signing_key, make_access_claims())

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'user_id': str(TEST_USER_ID)}


async def test_asks_the_auth_server_only_once(
    client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    token = make_token(signing_key, make_access_claims())

    for _ in range(5):
        await client.get(ME_URL, headers=bearer(token))

    # 요청마다 인증 서버에 묻지 않는다. 앱이 키를 기억한다
    assert auth_server.calls == 1


async def test_rejects_a_request_without_a_token(client: AsyncClient):
    response = await client.get(ME_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers['WWW-Authenticate'] == 'Bearer'


async def test_rejects_another_kind_of_authorization(client: AsyncClient):
    response = await client.get(ME_URL, headers={'Authorization': 'Basic dXNlcjpwYXNz'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_rejects_an_expired_token(client: AsyncClient, signing_key: SigningKey):
    token = make_token(signing_key, make_access_claims(exp=int(time.time()) - 60))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers['WWW-Authenticate'] == 'Bearer'


async def test_does_not_say_why_a_token_was_rejected(client: AsyncClient, signing_key: SigningKey):
    expired = make_token(signing_key, make_access_claims(exp=int(time.time()) - 60))
    refresh = make_token(signing_key, make_access_claims(token_type='refresh'))

    missing_response = await client.get(ME_URL)
    expired_response = await client.get(ME_URL, headers=bearer(expired))
    refresh_response = await client.get(ME_URL, headers=bearer(refresh))
    garbage_response = await client.get(ME_URL, headers=bearer('not-a-token'))

    # 어떤 이유로 거부됐든 응답이 같다
    assert missing_response.json() == expired_response.json() == refresh_response.json() == garbage_response.json()


async def test_reports_503_when_the_auth_server_is_down_and_no_key_is_known(
    client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.down = True
    token = make_token(signing_key, make_access_claims())

    response = await client.get(ME_URL, headers=bearer(token))

    # 401 이 아니다. 401 을 주면 프론트가 멀쩡한 사용자를 로그아웃시킨다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers['Retry-After'] == str(REFETCH_INTERVAL_SECONDS)


async def test_keeps_serving_logged_in_users_when_the_auth_server_goes_down(
    client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    token = make_token(signing_key, make_access_claims())
    await client.get(ME_URL, headers=bearer(token))

    auth_server.down = True
    response = await client.get(ME_URL, headers=bearer(token))

    # 인증 서버가 죽어도, 놀던 사용자는 계속 논다
    assert response.status_code == status.HTTP_200_OK


async def test_the_503_response_does_not_reveal_the_auth_server_address(
    client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.down = True

    response = await client.get(ME_URL, headers=bearer(make_token(signing_key, make_access_claims())))

    assert 'auth.test' not in response.text
    assert 'jwks' not in response.text.lower()
