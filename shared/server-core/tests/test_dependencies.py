# shared/server-core/tests/test_dependencies.py

"""
토큰을 받는 API 의 의존성(server_core/auth/dependencies.py)을 검증한다. 작은 앱(conftest.py 의 build_app)으로 본다.

  - CurrentUser: 토큰이 없거나 틀리면 401, 키를 구할 수 없으면 503
  - OptionalUser: 토큰을 보내지 않았으면 None. 보냈는데 틀렸으면 401(로그인하지 않은 것으로 넘기지 않는다)
  - 다시 동의할 항목이 남은 사람의 토큰(대상이 인증 서버뿐, #586)은 401
"""

from fastapi import status
from httpx import AsyncClient

from server_core.auth.jwks import REFETCH_INTERVAL_SECONDS
from server_core.testing.tokens import TEST_USER_ID, FakeAuthServer, SigningKey, make_access_claims, make_token
from tests.conftest import ME_URL, OPTIONAL_URL


def bearer(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


async def test_a_valid_token_reaches_the_api(client: AsyncClient, signing_key: SigningKey):
    token = make_token(signing_key, make_access_claims(adult_content=True, roles=['operator']))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'user_id': str(TEST_USER_ID), 'adult_content': True, 'is_operator': True}


async def test_without_a_token_it_is_unauthorized(client: AsyncClient):
    response = await client.get(ME_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers['WWW-Authenticate'] == 'Bearer'


async def test_a_token_of_someone_who_must_consent_again_is_unauthorized(client: AsyncClient, signing_key: SigningKey):
    # 인증 서버는 다시 동의할 필수 항목이 남은 사람에게 대상이 인증 서버뿐인 토큰을 준다(#586)
    token = make_token(signing_key, make_access_claims(aud=['ai-trpg-auth']))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_when_the_keys_cannot_be_fetched_it_is_unavailable(
    client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.down = True
    token = make_token(signing_key, make_access_claims())

    response = await client.get(ME_URL, headers=bearer(token))

    # 클라이언트의 잘못이 아니다. 로그아웃시키지 않는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers['Retry-After'] == str(REFETCH_INTERVAL_SECONDS)


async def test_the_optional_user_is_none_without_a_token(client: AsyncClient):
    response = await client.get(OPTIONAL_URL)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'user_id': None}


async def test_the_optional_user_is_the_owner_of_a_valid_token(client: AsyncClient, signing_key: SigningKey):
    token = make_token(signing_key, make_access_claims())

    response = await client.get(OPTIONAL_URL, headers=bearer(token))

    assert response.json() == {'user_id': str(TEST_USER_ID)}


async def test_a_wrong_token_is_not_treated_as_no_login(client: AsyncClient, signing_key: SigningKey):
    # 만료된 토큰을 가진 화면이 갱신할 때를 알아야 한다
    token = make_token(signing_key, make_access_claims(exp=1))

    response = await client.get(OPTIONAL_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_a_header_that_is_not_bearer_is_still_a_sent_token(client: AsyncClient):
    response = await client.get(OPTIONAL_URL, headers={'Authorization': 'Basic dXNlcjpwYXNz'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
