# asset-server/tests/test_service_auth.py

"""
다른 서버가 부르는 주소의 서명(app/core/service_auth.py)을 검증한다. 페르소나의 revision 을 묻는 주소로 본다.

보는 것.
  - 서명과 사용자의 토큰이 모두 맞아야 답한다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 남의 주소의 것이거나, 모르는 서버이거나, 그 서버의 비밀이 비었으면 401 이다.
    어느 경우든 같은 답이다. 토큰보다 서명을 먼저 본다
  - 쿼리까지 서명한다
  - 본문이 상한을 넘으면 서명을 보기 전에 413 이다(머리말로 알려도, 알리지 않고 보내도)
  - 이 파일은 app.* 를 가져오지 않는다(server_core 로 파일째 옮길 수 있게)
"""

import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.service_auth.signing import SIGNATURE_HEADER, TOLERANCE_SECONDS, sign
from server_core.testing.tokens import TEST_USER_ID, FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.service_auth import BODY_MAX_BYTES
from app.main import API_PREFIX, create_app
from tests.conftest import make_client, make_test_settings
from tests.signing import TEST_SECRETS, service_path, signed_get
from tests.test_content_boundary import imported_modules

pytestmark = pytest.mark.usefixtures('clean_tables')

SERVICE_AUTH = Path(__file__).resolve().parents[1] / 'app' / 'core' / 'service_auth.py'
BAD_SIGNATURE = {'detail': '요청의 서명이 맞지 않습니다.'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(TEST_USER_ID)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def persona(client: AsyncClient, mine: dict) -> dict:
    response = await client.post(f'{API_PREFIX}/personas', json={'name': '나'}, headers=mine)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
def revision(persona: dict) -> str:
    return f'/personas/{persona["id"]}/revision'


async def test_answers_with_a_signature_and_the_users_token(client: AsyncClient, mine: dict, persona: dict):
    response = await signed_get(client, f'/personas/{persona["id"]}/revision', mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'id': persona['id'], 'revision': 1}


async def test_without_a_signature_it_is_401_even_with_a_token(client: AsyncClient, mine: dict, revision: str):
    response = await client.get(service_path('chat', revision), headers=mine)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == BAD_SIGNATURE


async def test_the_signature_is_checked_before_the_token(client: AsyncClient, revision: str):
    unsigned = await client.get(service_path('chat', revision))
    signed = await signed_get(client, revision)

    # 서명이 틀리면 토큰을 보기 전에 끝난다. 서명이 맞으면 그다음에 토큰이 없다고 답한다
    assert (unsigned.status_code, unsigned.json()) == (status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE)
    assert signed.status_code == status.HTTP_401_UNAUTHORIZED
    assert signed.json() != BAD_SIGNATURE


def at_run_time(wrong: dict) -> dict:
    """
    drift(초)를 테스트가 도는 때의 sent_at 으로 바꾼다. 수집할 때 시각을 굳히면 스위트가 길어질수록
    "너무 새" 서명이 허용 범위 안으로 들어온다.
    """
    if 'drift' not in wrong:
        return wrong
    return {'sent_at': int(time.time()) + wrong['drift']}


@pytest.mark.parametrize(
    'wrong',
    [
        {'secret': 'a-different-secret-0123456789abcdef'},
        {'drift': -TOLERANCE_SECONDS - 60},
        {'drift': TOLERANCE_SECONDS + 60},
        {'signed_as': f'{API_PREFIX}/service/chat/personas/{uuid.UUID(int=1)}/revision'},
        # 모르는 서버. 비밀이 없으니 chat 의 비밀로 서명해도 받지 않는다
        {'caller': 'board'},
        # 다른 서버의 비밀. story 의 이름으로 chat 의 비밀을 쓰면 받지 않는다
        {'caller': 'story', 'secret': TEST_SECRETS['chat']},
    ],
    ids=['wrong-secret', 'too-old', 'too-new', 'another-path', 'unknown-caller', 'another-servers-secret'],
)
async def test_refuses_signatures_it_cannot_accept(client: AsyncClient, mine: dict, revision: str, wrong: dict):
    response = await signed_get(client, revision, mine, **at_run_time(wrong))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == BAD_SIGNATURE


async def test_a_caller_name_out_of_shape_is_not_a_route(client: AsyncClient, mine: dict, revision: str):
    response = await signed_get(client, revision, mine, caller='Chat')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_an_empty_secret_accepts_nothing(auth_server: FakeAuthServer, engine: AsyncEngine, mine: dict):
    app = create_app(make_test_settings(chat_server_secret=''), http_client=auth_server.make_client(), engine=engine)
    async with make_client(app) as client:
        made = await client.post(f'{API_PREFIX}/personas', json={'name': '나'}, headers=mine)
        # 비밀이 비었을 때 빈 비밀로 서명한 것도 받지 않는다
        response = await signed_get(client, f'/personas/{made.json()["id"]}/revision', mine, secret='')
    await app.state.http_client.aclose()

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_query_is_signed_too(client: AsyncClient, mine: dict, revision: str):
    path = service_path('chat', revision)
    signature = sign(TEST_SECRETS['chat'], int(time.time()), 'GET', f'{path}?view=short', b'')

    same = await client.get(f'{path}?view=short', headers={**mine, SIGNATURE_HEADER: signature})
    changed = await client.get(f'{path}?view=long', headers={**mine, SIGNATURE_HEADER: signature})

    assert same.status_code == status.HTTP_200_OK
    assert changed.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_body_is_signed_as_sent(client: AsyncClient, mine: dict, revision: str):
    path = service_path('chat', revision)
    body = b'x' * BODY_MAX_BYTES
    signature = sign(TEST_SECRETS['chat'], int(time.time()), 'GET', path, body)

    accepted = await client.request('GET', path, content=body, headers={**mine, SIGNATURE_HEADER: signature})
    changed = await client.request('GET', path, content=b'y' + body[1:], headers={**mine, SIGNATURE_HEADER: signature})

    assert accepted.status_code == status.HTTP_200_OK
    assert changed.status_code == status.HTTP_401_UNAUTHORIZED


async def test_a_body_over_the_limit_is_413_before_the_signature(client: AsyncClient, revision: str):
    response = await client.request('GET', service_path('chat', revision), content=b'x' * (BODY_MAX_BYTES + 1))

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_declared_length_over_the_limit_is_413_without_reading(client: AsyncClient, revision: str):
    # 머리말만 보고 거절한다. 본문을 끝까지 받기 전에 끊는다(여기서는 본문이 비어 있어도 413 이다)
    headers = {'Content-Length': str(BODY_MAX_BYTES + 1)}

    response = await client.request('GET', service_path('chat', revision), headers=headers)

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_streamed_body_over_the_limit_is_413_too(client: AsyncClient, revision: str):
    async def chunks() -> AsyncIterator[bytes]:
        # 길이를 알리지 않고(chunked) 보낸다. 머리말을 믿지 않고 읽으면서 센다
        for _ in range(BODY_MAX_BYTES // 1024 + 1):
            yield b'x' * 1024

    response = await client.request('GET', service_path('chat', revision), content=chunks())

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


def test_service_auth_imports_nothing_from_the_app():
    assert [name for name in imported_modules(SERVICE_AUTH) if name.startswith(('app', '.'))] == []


async def test_every_service_route_needs_the_signature(app: FastAPI, client: AsyncClient, mine: dict):
    # 서명을 보는 주소는 모두 /api/v1/asset/service/ 아래다. 프록시가 그 아래를 바깥에 열지 않는다
    # (docker/nginx/templates/api.inc.template). 그 아래의 주소는 모두 서명이 없으면 401 이다(토큰이 있어도)
    some_id = str(uuid.UUID(int=1))
    routes = [
        (method.upper(), path)
        for path, operations in app.openapi()['paths'].items()
        if path.startswith(f'{API_PREFIX}/service/')
        for method in operations
    ]
    answers = {}
    for method, path in routes:
        url = path.format(caller='chat', persona_id=some_id, character_id=some_id, world_id=some_id, public_id=some_id)
        answer = await client.request(method, url, headers=mine, json={'withdrawn_at': '2026-10-28T03:00:00Z'})
        answers[(method, path)] = (answer.status_code, answer.json())

    assert len(routes) == 7
    assert answers == {route: (status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE) for route in routes}
