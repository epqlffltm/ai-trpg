# notification-server/tests/test_put_notifications.py

"""
다른 서버가 알림을 넣는 API(POST /api/v1/notification/service/{source}/notifications)를 검증한다.

  - 서명이 맞으면 넣는다. 같은 알림을 다시 보내면 같은 줄로 답한다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 남의 주소의 것이거나, 그 서버의 비밀이 없으면 401 이다
  - 서명을 확인한 뒤에 본문을 본다. 모양이 틀리면 422 다
  - 그 서버가 넣을 수 없는 kind 이거나 꼭 있어야 하는 칸이 빠졌으면 422 다(app/notifications/catalog.py)
"""

import asyncio
import logging
import time
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import create_app
from app.notifications.models import Notification
from app.notifications.router import BODY_MAX_BYTES, KIND_REFUSED_ERROR_CODE
from app.notifications.schemas import PAYLOAD_INPUT_MAX_BYTES, compact_size
from app.service_auth.signing import SIGNATURE_HEADER, TOLERANCE_SECONDS
from tests.conftest import make_client, make_test_settings
from tests.logs import rendered
from tests.signing import TEST_SECRETS, put_path, signed_put

pytestmark = pytest.mark.usefixtures('clean_tables')

USER = '0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a'

# 게임 서버가 넣는 시나리오 제재 알림의 값. 꼭 있어야 하는 칸이 모두 있다
SANCTIONED = {
    'scenario_id': '9d1c2b3a-4e5f-4a6b-8c7d-0e1f2a3b4c5d',
    'title': '잊힌 탑',
    'version_number': 3,
    'publishing_banned': False,
}


def make_body(**overrides) -> dict:
    body = {
        'source_key': 'scenario-sanction:1',
        'user_id': USER,
        'kind': 'scenario.sanctioned',
        'payload': SANCTIONED,
    }
    body.update(overrides)
    return body


async def count_rows(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Notification))


# --- 넣기 ---


async def test_puts_a_notification(client: AsyncClient, session: AsyncSession):
    response = await signed_put(client, make_body())

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['status'] == 'created'
    saved = await session.get(Notification, response.json()['id'])
    assert (saved.source, saved.source_key, saved.kind) == ('game', 'scenario-sanction:1', 'scenario.sanctioned')
    assert saved.user_id == uuid.UUID(USER)
    assert saved.payload == make_body()['payload']
    assert saved.read_at is None


async def test_sending_the_same_notification_again_answers_with_the_same_row(
    client: AsyncClient, session: AsyncSession
):
    # 넣는 서버가 답을 못 받아 다시 보낸 것이다
    first = await signed_put(client, make_body())
    again = await signed_put(client, make_body())

    assert again.status_code == status.HTTP_200_OK
    assert again.json() == {'id': first.json()['id'], 'status': 'existing'}
    assert await count_rows(session) == 1


@pytest.mark.parametrize(
    'change',
    [
        {'user_id': 'b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e'},
        {'kind': 'publishing.unbanned'},
        {'payload': {**SANCTIONED, 'scenario_id': 'another'}},
    ],
)
async def test_another_notification_with_the_same_key_is_refused(
    client: AsyncClient, session: AsyncSession, change: dict
):
    await signed_put(client, make_body())

    response = await signed_put(client, make_body(**change))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['detail'] == {'code': 'key_reused', 'source_key': 'scenario-sanction:1'}
    assert await count_rows(session) == 1


async def test_the_same_key_from_another_server_is_another_notification(client: AsyncClient, session: AsyncSession):
    await signed_put(client, make_body(), source='game')

    paid = {'order_id': 'o-1', 'product_id': 'credits-1000', 'price': 1000, 'credits': '1000'}
    response = await signed_put(client, make_body(kind='order.paid', payload=paid), source='billing')

    assert response.status_code == status.HTTP_201_CREATED
    assert await count_rows(session) == 2


async def test_the_same_key_sent_at_once_is_one_row(client: AsyncClient, session: AsyncSession):
    # 넣는 서버의 워커 둘이 같은 줄을 동시에 보냈다. DB 가 하나만 넣는다
    responses = await asyncio.gather(*(signed_put(client, make_body()) for _ in range(5)))

    assert sorted(response.status_code for response in responses) == [200, 200, 200, 200, 201]
    assert len({response.json()['id'] for response in responses}) == 1
    assert await count_rows(session) == 1


# --- 서명 ---


async def test_refuses_a_request_without_a_signature(client: AsyncClient, session: AsyncSession):
    response = await client.post(put_path('game'), json=make_body())

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await count_rows(session) == 0


async def test_refuses_a_signature_made_with_another_servers_secret(client: AsyncClient, session: AsyncSession):
    # 결제 서버의 비밀로 게임 서버인 척 넣을 수 없다
    response = await signed_put(client, make_body(), source='game', secret=TEST_SECRETS['billing'])

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await count_rows(session) == 0


async def test_refuses_a_signature_taken_from_another_address(client: AsyncClient):
    # 게임 서버의 비밀로 서명했지만 결제 서버의 주소로 서명한 것을 게임 서버의 주소에 붙였다
    response = await signed_put(client, make_body(), source='game', signed_as=put_path('billing'))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_refuses_an_old_signature(client: AsyncClient):
    response = await signed_put(client, make_body(), sent_at=int(time.time()) - TOLERANCE_SECONDS - 60)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_refuses_a_body_changed_after_signing(client: AsyncClient):
    good = await signed_put(client, make_body())
    header = good.request.headers[SIGNATURE_HEADER]

    response = await client.post(
        put_path('game'),
        content=b'{"source_key":"x","user_id":"' + USER.encode() + b'","kind":"a","payload":{}}',
        headers={SIGNATURE_HEADER: header},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_refuses_an_unknown_server_like_a_bad_signature(client: AsyncClient):
    # 404 가 아니다. 어느 이름이 있는지 알리지 않는다
    response = await signed_put(client, make_body(), source='chat', secret='a-made-up-secret-that-is-long-012')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_refuses_a_server_whose_secret_is_not_set(engine: AsyncEngine):
    app = create_app(make_test_settings(board_server_secret=''), engine=engine)

    async with make_client(app) as client:
        response = await signed_put(client, make_body(), source='board', secret='')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 본문 ---


async def test_refuses_a_body_too_large_before_checking_the_signature(client: AsyncClient):
    response = await signed_put(client, b'{' + b' ' * BODY_MAX_BYTES + b'}')

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_refuses_a_streamed_body_too_large_without_a_length(client: AsyncClient):
    # 길이를 미리 알리지 않고 조각으로 보내도 상한에서 끊는다
    async def chunks():
        for _ in range(BODY_MAX_BYTES // 1024 + 2):
            yield b' ' * 1024

    response = await client.post(put_path('game'), content=chunks())

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


@pytest.mark.parametrize(
    'body',
    [
        b'not json',
        make_body(source_key=''),
        make_body(source_key='has space'),
        make_body(source_key='x' * 129),
        make_body(user_id='not-a-uuid'),
        make_body(kind='Scenario.Sanctioned'),
        make_body(kind='scenario..sanctioned'),
        make_body(payload=['not', 'an', 'object']),
        make_body(payload={'text': 'x' * PAYLOAD_INPUT_MAX_BYTES}),
        {**make_body(), 'source': 'billing'},
        {key: value for key, value in make_body().items() if key != 'kind'},
    ],
)
async def test_refuses_a_body_of_the_wrong_shape(client: AsyncClient, session: AsyncSession, body: object):
    response = await signed_put(client, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await count_rows(session) == 0


async def test_the_largest_payload_fits_the_database(client: AsyncClient):
    # 받는 상한(빈칸 없이 2048바이트)에 꽉 찬 값도 DB 의 상한(jsonb 글자 4096바이트) 안에 든다
    # 작은 값이 많을수록 DB 가 넣는 빈칸이 는다(쉼표와 쌍점마다 하나). 가장 나쁜 모양으로 상한까지 채운다
    many_small: dict[str, int] = {}
    while compact_size({**many_small, f'k{len(many_small)}': 0}) <= PAYLOAD_INPUT_MAX_BYTES:
        many_small[f'k{len(many_small)}'] = 0

    # 꼭 있어야 하는 칸이 없는 kind 로 보낸다. 표에 없는 칸은 받는다
    response = await signed_put(client, make_body(kind='publishing.unbanned', payload=many_small))

    assert response.status_code == status.HTTP_201_CREATED


async def test_the_docs_list_the_put_address(engine: AsyncEngine, app: FastAPI):
    debug_app = create_app(make_test_settings(debug=True), engine=engine)

    async with make_client(debug_app) as client:
        paths = (await client.get('/api/v1/notification/openapi.json')).json()['paths']

    assert list(paths['/api/v1/notification/service/{source}/notifications']) == ['post']


# --- 알림의 종류 ---


async def test_refuses_a_kind_that_is_not_listed(client: AsyncClient, session: AsyncSession):
    response = await signed_put(client, make_body(kind='scenario.restored'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == {'code': 'kind_unknown', 'kind': 'scenario.restored'}
    assert await count_rows(session) == 0


async def test_refuses_a_kind_from_a_server_that_does_not_own_it(client: AsyncClient, session: AsyncSession):
    # 게시판 서버의 서명은 맞지만 결제 완료는 결제 서버만 넣는다. 화면에는 진짜 결제 알림처럼 보일 것이다
    paid = {'order_id': 'o-1', 'product_id': 'credits-1000', 'price': 1000, 'credits': '1000'}

    response = await signed_put(client, make_body(kind='order.paid', payload=paid), source='board')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == {'code': 'kind_not_allowed', 'kind': 'order.paid'}
    assert await count_rows(session) == 0


async def test_refuses_a_payload_without_the_fields_the_screen_needs(client: AsyncClient, session: AsyncSession):
    payload = {key: value for key, value in SANCTIONED.items() if key not in ('title', 'version_number')}

    response = await signed_put(client, make_body(payload=payload))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == {
        'code': 'payload_missing_fields',
        'kind': 'scenario.sanctioned',
        'missing': ['title', 'version_number'],
    }
    assert await count_rows(session) == 0


async def test_a_field_that_is_null_is_there(client: AsyncClient):
    # 지금 라운드에 바꾸지 못했으면 게임 서버는 round 와 price 를 null 로 싣는다
    payload = {
        'table_id': 't-1',
        'title': '탑',
        'from': 'old-model',
        'narration_model': 'new-model',
        'reason': 'retired',
        'round': None,
        'price': None,
    }

    response = await signed_put(client, make_body(kind='narration_model.replaced', payload=payload))

    assert response.status_code == status.HTTP_201_CREATED


async def test_a_refusal_is_logged_without_the_receiver_or_the_payload(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    payload = {'scenario_id': 'secret-scenario'}

    with caplog.at_level(logging.WARNING, logger='app.notifications.router'):
        await signed_put(client, make_body(payload=payload))

    (entry,) = rendered(caplog.records, 'app.notifications.router')
    assert entry['level'] == 'warning'
    assert entry['error_code'] == KIND_REFUSED_ERROR_CODE
    assert (entry['source'], entry['kind']) == ('game', 'scenario.sanctioned')
    assert entry['refusal'] == 'payload_missing_fields'
    assert entry['missing_fields'] == 'publishing_banned,title,version_number'
    assert USER not in str(entry) and 'secret-scenario' not in str(entry)


async def test_the_kind_is_checked_before_the_key(client: AsyncClient, session: AsyncSession):
    # 같은 열쇠의 줄이 있어도 표에 맞지 않으면 409 가 아니라 422 다. 고칠 것은 kind 다
    await signed_put(client, make_body())

    response = await signed_put(client, make_body(kind='scenario.restored'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await count_rows(session) == 1
