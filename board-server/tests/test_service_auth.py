# board-server/tests/test_service_auth.py

"""
인증 서버의 서명을 확인하는 문지기(app/core/service_auth.py).

서명의 셈은 HTTP 없이 보고, 경로와 쿼리, 비밀이 빈 설정은 앱에 요청을 보내 본다.
탈퇴를 받는 주소의 시나리오는 계약 시험(contract/tests/test_withdrawals.py)이 본다.
"""

import time
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.service_auth.signing import SIGNATURE_HEADER, TOLERANCE_SECONDS, sign

from app.core.config import Settings
from app.core.service_auth import BAD_SIGNATURE_DETAIL, is_valid_signature, now_seconds
from app.main import create_app
from tests.conftest import TEST_AUTH_SECRET, make_client, make_test_settings

SECRET = 'x' * 40
PATH = '/api/v1/board/service/users/6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5f/withdrawal'
BODY = b'{"withdrawn_at":"2026-10-28T03:00:00+00:00"}'
NOW = 1_793_156_400


def accepts(header: str | None, **overrides) -> bool:
    """이 요청을 받아들이는가. 바꿔 볼 것만 넘긴다."""
    return is_valid_signature(
        overrides.get('secret', SECRET),
        header,
        overrides.get('method', 'POST'),
        overrides.get('path', PATH),
        overrides.get('body', BODY),
        overrides.get('now', NOW),
    )


def signed(secret: str = SECRET, sent_at: int = NOW, body: bytes = BODY) -> str:
    return sign(secret, sent_at, 'POST', PATH, body)


def test_accepts_signature_of_the_same_request():
    assert accepts(signed())


def test_accepts_signature_made_by_python_hmac_like_the_auth_server():
    # NestJS 때의 시험(src/service-auth/signing.spec.ts)과 같은 값이다
    header = 't=1793156400,v1=474f425581b4385c441f17cd46ba37d0729b254f888587257b1415da1a644ce1'
    assert accepts(header)


@pytest.mark.parametrize(
    'overrides',
    [
        {'secret': 'y' * 40},
        {'method': 'PUT'},
        {'path': PATH.replace('6f1e', '7f1e')},
        {'body': BODY.replace(b'28', b'29')},
    ],
)
def test_rejects_signature_of_another_request(overrides: dict):
    assert not accepts(signed(), **overrides)


def test_rejects_signature_older_or_newer_than_tolerance():
    header = signed()
    assert accepts(header, now=NOW + TOLERANCE_SECONDS)
    assert not accepts(header, now=NOW + TOLERANCE_SECONDS + 1)
    assert not accepts(header, now=NOW - TOLERANCE_SECONDS - 1)


@pytest.mark.parametrize('secret', ['', 'z' * 31])
def test_rejects_everything_when_secret_is_empty_or_short(secret: str):
    assert not accepts(signed(secret), secret=secret)


@pytest.mark.parametrize(
    'header',
    [
        None,
        '',
        f't={NOW}',
        f'v1={"a" * 64}',
        f't=abc,v1={"a" * 64}',
        f't={NOW},v1={"A" * 64}',
        f't={NOW},v1={"a" * 63}',
        f't={NOW},v1={"a" * 64}\n',
        f't={"1" * 20},v1={"a" * 64}',
    ],
)
def test_rejects_malformed_header(header: str | None):
    assert not accepts(header)


def test_time_is_read_as_a_number_like_nest():
    # 서명은 "1793156400" 으로 셈했고 머리말은 앞에 0 을 붙였다. NestJS 때도 받았다
    digest = signed().split(',v1=')[1]
    assert accepts(f't=00{NOW},v1={digest}')


def test_now_seconds_is_whole_seconds():
    assert abs(now_seconds() - time.time()) < 1


# 앱에 보내 보기


def withdrawal_path(user_id: object) -> str:
    return f'/api/v1/board/service/users/{user_id}/withdrawal'


async def post_signed(client: AsyncClient, url: str, signed_path: str, secret: str = TEST_AUTH_SECRET):
    body = b'{"withdrawn_at": "2026-10-28T03:00:00Z"}'
    header = sign(secret, int(time.time()), 'POST', signed_path, body)
    return await client.post(url, content=body, headers={SIGNATURE_HEADER: header, 'Content-Type': 'application/json'})


@pytest.mark.usefixtures('clean_tables')
async def test_query_is_part_of_the_signed_path(client: AsyncClient):
    path = withdrawal_path(uuid.uuid4())

    response = await post_signed(client, f'{path}?retry=1', f'{path}?retry=1')

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures('clean_tables')
async def test_path_is_signed_as_received_without_decoding(client: AsyncClient):
    # 받은 그대로(%2D)에 서명한다. 풀어 쓴 경로(-)로 한 서명은 맞지 않는다
    user_id = str(uuid.uuid4())
    encoded = withdrawal_path(user_id.replace('-', '%2D', 1))

    accepted = await post_signed(client, encoded, encoded)
    rejected = await post_signed(client, encoded, withdrawal_path(user_id))

    assert accepted.status_code == status.HTTP_200_OK
    assert rejected.status_code == status.HTTP_401_UNAUTHORIZED


async def test_missing_signature_is_401_with_nest_text(client: AsyncClient):
    response = await client.post(withdrawal_path(uuid.uuid4()), json={'withdrawn_at': '2026-10-28T03:00:00Z'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {'detail': BAD_SIGNATURE_DETAIL}
    assert 'www-authenticate' not in response.headers


async def test_signature_is_checked_before_the_path_and_the_body(client: AsyncClient):
    response = await client.post(withdrawal_path('not-a-uuid'), json={'email': 'a@b.c'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_empty_secret_refuses_every_signature(app_settings_without_secret: Settings, engine):
    app = create_app(app_settings_without_secret, engine=engine)
    path = withdrawal_path(uuid.uuid4())
    async with make_client(app) as client:
        response = await post_signed(client, path, path, secret='')
    await app.state.http_client.aclose()

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {'detail': BAD_SIGNATURE_DETAIL}


@pytest.fixture
def app_settings_without_secret() -> Settings:
    return make_test_settings(auth_server_secret='')
