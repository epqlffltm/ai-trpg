# board-server/contract/tests/test_auth.py

"""
토큰 검증(board-server/test/auth.e2e-spec.ts). 문지기가 실제로 걸려 있는가, 응답의 상태 코드와 머리말과 모양이 맞는가.

키는 가짜 인증 서버(auth_server)가 내준다. 서버는 한 번 받은 키를 기억해 쓰므로, 인증 서버가 죽은 뒤에도
이미 받은 키로 토큰을 검증한다. 끊긴 세션의 목록은 늘 비어 있어 여기서 보지 않는다.
"""

from collections.abc import Callable

import httpx
import pytest

from harness.auth import FakeAuthServer
from harness.tokens import bearer, forge_token, make_signing_key, make_token, valid_claims
from tests.conftest import SIGNING_KID
from tests.urls import API, HEALTH, ME, READY

UNAUTHORIZED = {'detail': '인증이 필요합니다.'}


def test_valid_token_returns_owner_id(client: httpx.Client, headers_for: Callable[..., dict[str, str]], user_id: str):
    response = client.get(ME, headers=headers_for(user_id))

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'user_id': user_id, 'is_operator': False}


def test_operator_role_is_reported(client: httpx.Client, headers_for: Callable[..., dict[str, str]], user_id: str):
    response = client.get(ME, headers=headers_for(user_id, roles=['operator']))

    assert response.status_code == httpx.codes.OK
    assert response.json()['is_operator'] is True


@pytest.mark.parametrize(
    'roles',
    [
        pytest.param(None, id='roles 가 없는 토큰'),
        pytest.param('operator', id='roles 가 목록이 아닌 토큰'),
    ],
)
def test_odd_roles_are_accepted_but_not_operator(
    client: httpx.Client, headers_for: Callable[..., dict[str, str]], user_id: str, roles: object
):
    response = client.get(ME, headers=headers_for(user_id, roles=roles))

    assert response.status_code == httpx.codes.OK
    assert response.json()['is_operator'] is False


def test_missing_token_is_401_with_bearer_challenge(client: httpx.Client):
    response = client.get(ME)

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.headers['www-authenticate'] == 'Bearer'
    assert response.json() == UNAUTHORIZED


def test_non_bearer_scheme_is_401(client: httpx.Client):
    response = client.get(ME, headers={'Authorization': 'Basic dXNlcjpwYXNz'})

    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.parametrize(
    ('subject', 'options'),
    [
        pytest.param(None, {'expires_in': -60}, id='만료된 토큰'),
        pytest.param(None, {'audience': ['ai-trpg-game']}, id='다른 서버에만 쓰라고 발급된 토큰'),
        pytest.param(None, {'issuer': 'someone-else'}, id='다른 곳이 발급한 토큰'),
        pytest.param(None, {'token_type': 'refresh'}, id='refresh 토큰'),
        pytest.param(None, {'kid': 'forged'}, id='모르는 kid 의 토큰'),
        pytest.param('42', {}, id='주인의 ID 가 UUID 가 아닌 토큰'),
    ],
)
def test_rejected_tokens_are_401_without_reason(
    client: httpx.Client,
    token_for: Callable[..., str],
    user_id: str,
    subject: str | None,
    options: dict[str, object],
):
    response = client.get(ME, headers=bearer(token_for(subject or user_id, **options)))

    assert response.status_code == httpx.codes.UNAUTHORIZED
    # 어느 경우든 응답이 똑같다. 무엇이 틀렸는지 응답으로는 가릴 수 없다
    assert response.json() == UNAUTHORIZED
    assert response.headers['www-authenticate'] == 'Bearer'


def test_token_signed_by_other_key_with_same_kid_is_401(client: httpx.Client, user_id: str):
    # 인증 서버의 것이 아닌 키. kid 만 같다
    stranger = make_signing_key(SIGNING_KID)

    response = client.get(ME, headers=bearer(make_token(stranger, user_id)))

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_unsigned_none_token_is_401(client: httpx.Client, user_id: str):
    token = forge_token({'alg': 'none', 'kid': SIGNING_KID}, valid_claims(user_id))

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_garbage_token_is_401(client: httpx.Client):
    response = client.get(ME, headers=bearer('not-a-token'))

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_health_and_ready_answer_without_token(client: httpx.Client):
    assert client.get(HEALTH).status_code == httpx.codes.OK
    assert client.get(READY).status_code == httpx.codes.OK


def test_unknown_path_is_404_not_401(client: httpx.Client):
    response = client.get(f'{API}/no-such-api')

    assert response.status_code == httpx.codes.NOT_FOUND


def test_missing_token_is_still_401_when_auth_server_is_down(client: httpx.Client, auth_server: FakeAuthServer):
    auth_server.set_failing(True)

    response = client.get(ME)

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_keys_once_fetched_are_used_after_auth_server_dies(
    client: httpx.Client, auth_server: FakeAuthServer, headers_for: Callable[..., dict[str, str]], user_id: str
):
    headers = headers_for(user_id)
    assert client.get(ME, headers=headers).status_code == httpx.codes.OK
    calls = auth_server.calls()

    auth_server.set_failing(True)
    response = client.get(ME, headers=headers)

    assert response.status_code == httpx.codes.OK
    # 요청마다 인증 서버에 묻지 않고 기억한 키를 쓴다
    assert auth_server.calls() == calls


def test_unknown_kids_do_not_flood_auth_server(
    client: httpx.Client, auth_server: FakeAuthServer, token_for: Callable[..., str], user_id: str
):
    calls = auth_server.calls()

    for index in range(5):
        response = client.get(ME, headers=bearer(token_for(user_id, kid=f'forged-{index}')))
        assert response.status_code == httpx.codes.UNAUTHORIZED

    # 모르는 kid 가 오면 다시 받아 보지만, 정한 간격에 한 번만 시도한다
    assert auth_server.calls() - calls <= 1


def test_public_endpoints_answer_while_auth_server_is_down(client: httpx.Client, auth_server: FakeAuthServer):
    auth_server.set_failing(True)

    response = client.get(READY)

    assert response.status_code == httpx.codes.OK
