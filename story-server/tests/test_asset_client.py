# story-server/tests/test_asset_client.py

"""
asset 서버를 부르는 것(app/assets/client.py)을 검증한다. 가짜 HTTP(httpx.MockTransport)로 돈다. DB 를 쓰지 않는다.

보는 것.
  - 주소와 서명: 이 서버의 이름(story)의 주소로, 이 서버의 비밀로 서명하고(asset 서버의 is_valid 로 확인한다),
    사용자의 토큰을 함께 넘긴다
  - 답: 200 은 그 모양으로 읽고, 검사하지 않는 칸(시간대, 인물, 이벤트, 엔딩)도 남긴다. 앞 형식(1)의 판도 읽는다.
    404, 403 adult_content_required 는 각각의 예외다.
    그 밖의 답, 모양이 틀린 답, 이 서버가 모르는 형식의 판, 닿지 못함, 주소가 없음은 모두 AssetUnavailableError 다
"""

import json
import time
import uuid

import httpx
import pytest
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

from app.assets.client import (
    AssetAdultRequiredError,
    AssetClient,
    AssetNotFoundError,
    AssetUnavailableError,
    persona_path,
    world_path,
)
from app.assets.schemas import WORLD_FORMAT_MAX
from tests.assets import make_persona, make_world, world_document

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'
WORLD_ID = uuid.UUID('22222222-3333-4444-8555-666666666666')


def client_answering(handler, base_url: str = BASE_URL + '/') -> AssetClient:
    return AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), base_url, SECRET, 3.0)


def answer(status_code: int, body: object) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})


def copy_body(**document) -> dict:
    """asset 서버가 내주는 WorldCopy 의 JSON. document 로 문서의 칸을 덮어쓴다."""
    return {
        'id': str(WORLD_ID),
        'version': 2,
        'rating': 'all',
        'published_at': '2026-10-24T00:00:00Z',
        'document': world_document(**document),
    }


async def test_a_world_is_fetched_with_a_signature_and_the_token():
    copy = make_world(WORLD_ID)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(200, copy.model_dump(mode='json'))

    fetched = await client_answering(handler).fetch_world(TOKEN, WORLD_ID)

    (request,) = seen
    path = f'/api/v1/asset/service/story/worlds/{WORLD_ID}/latest'
    assert (request.method, str(request.url)) == ('GET', BASE_URL + path)
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', path, b'', time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert request.extensions['timeout']['read'] == 3.0
    assert fetched == copy


def test_the_path_carries_this_servers_name():
    assert world_path(WORLD_ID) == f'/api/v1/asset/service/story/worlds/{WORLD_ID}/latest'
    assert persona_path(WORLD_ID) == f'/api/v1/asset/service/story/personas/{WORLD_ID}'


async def test_a_persona_is_fetched_with_a_signature_and_the_token():
    copy = make_persona(WORLD_ID)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(200, {**copy.model_dump(mode='json'), 'owner_note': '여기서 읽지 않는 칸'})

    fetched = await client_answering(handler).fetch_persona(TOKEN, WORLD_ID)

    (request,) = seen
    path = f'/api/v1/asset/service/story/personas/{WORLD_ID}'
    assert (request.method, str(request.url)) == ('GET', BASE_URL + path)
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', path, b'', time.time())
    assert fetched == copy


async def test_a_missing_persona_is_not_found():
    with pytest.raises(AssetNotFoundError):
        await client_answering(lambda request: answer(404, {'detail': '없음'})).fetch_persona(TOKEN, WORLD_ID)


async def test_fields_not_checked_here_are_kept():
    fetched = await client_answering(lambda request: answer(200, copy_body())).fetch_world(TOKEN, WORLD_ID)

    document = fetched.document.model_dump(mode='json')
    assert document == world_document()
    assert (document['cast'][0]['id'], document['events'][0]['id'], document['endings'][0]['id']) == (
        'mina',
        'meet',
        'solo',
    )


async def test_an_older_format_is_read():
    body = copy_body(fmt=1)
    del body['document']['events'], body['document']['endings']

    fetched = await client_answering(lambda request: answer(200, body)).fetch_world(TOKEN, WORLD_ID)

    assert fetched.document.format == 1


@pytest.mark.parametrize(
    ('response', 'error'),
    [
        (answer(404, {'detail': '찾을 수 없습니다.'}), AssetNotFoundError),
        (answer(403, {'detail': '...', 'code': 'adult_content_required'}), AssetAdultRequiredError),
        (answer(403, {'detail': '...', 'code': 'something_else'}), AssetUnavailableError),
        (httpx.Response(403, content=b'not json'), AssetUnavailableError),
        (answer(401, {'detail': '요청의 서명이 맞지 않습니다.'}), AssetUnavailableError),
        (answer(500, {'detail': 'boom'}), AssetUnavailableError),
        (answer(200, {'id': 'not-a-uuid'}), AssetUnavailableError),
        (answer(200, copy_body(fmt=WORLD_FORMAT_MAX + 1)), AssetUnavailableError),
        (answer(200, copy_body(name=None)), AssetUnavailableError),
    ],
    ids=['404', 'adult', 'other-403', '403-not-json', '401', '500', 'bad-shape', 'unknown-format', 'no-name'],
)
async def test_answers_become_the_three_errors(response: httpx.Response, error: type[Exception]):
    with pytest.raises(error):
        await client_answering(lambda request: response).fetch_world(TOKEN, WORLD_ID)


async def test_unreachable_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(AssetUnavailableError, match='ConnectError'):
        await client_answering(handler).fetch_world(TOKEN, WORLD_ID)


async def test_without_an_address_nothing_is_called():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError('부르면 안 된다')

    with pytest.raises(AssetUnavailableError, match='ASSET_URL'):
        await client_answering(handler, base_url='').fetch_world(TOKEN, WORLD_ID)
