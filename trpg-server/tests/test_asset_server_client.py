# trpg-server/tests/test_asset_server_client.py

"""
asset 서버를 부르는 것(app/asset_server/client.py)을 검증한다. 가짜 HTTP(httpx.MockTransport)로 돈다. DB 를 쓰지 않는다.

보는 것.
  - 주소와 서명: 이 서버의 이름(trpg)의 주소로, 이 서버의 비밀로 본문까지 서명한다(asset 서버의 is_valid 로 확인한다)
  - 맡기기와 지우기는 그린 사람의 토큰을 함께 넘긴다. 받기(kept)는 토큰을 넘기지 않는다
  - 답: 201 은 그림의 id 로, 200 은 바이트와 형식으로 읽는다. 404 는 AssetNotFoundError,
    그 밖의 답, 그림이 아닌 답, 모양이 틀린 답, 닿지 못함, 주소가 없음은 모두 AssetUnavailableError 다
  - 설정: ASSET_URL 을 적었으면 32자 이상의 ASSET_SECRET 이 있어야 뜬다
"""

import json
import time
import uuid

import httpx
import pytest
from pydantic import ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

from app.asset_server.client import (
    AssetClient,
    AssetNotFoundError,
    AssetUnavailableError,
    ImageContent,
    images_path,
    kept_path,
)
from tests.conftest import make_test_settings

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'
IMAGE_ID = uuid.UUID('33333333-2222-4333-8444-555555555555')
PNG = b'\x89PNG fake'


def client_answering(handler, base_url: str = BASE_URL + '/') -> AssetClient:
    return AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), base_url, SECRET, 3.0)


def answer(status_code: int, body: object) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})


def test_the_paths_carry_this_servers_name():
    assert images_path() == '/api/v1/asset/service/trpg/images'
    assert kept_path(IMAGE_ID) == f'/api/v1/asset/service/trpg/images/{IMAGE_ID}/kept'


async def test_an_image_is_kept_with_a_signed_body_and_the_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(201, {'id': str(IMAGE_ID), 'mime_type': 'image/png'})

    kept = await client_answering(handler).keep_image(TOKEN, PNG)

    (request,) = seen
    path = '/api/v1/asset/service/trpg/images'
    assert (request.method, str(request.url), request.content) == ('POST', BASE_URL + path, PNG)
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'POST', path, PNG, time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert request.extensions['timeout']['read'] == 3.0
    assert kept == IMAGE_ID


async def test_a_kept_image_is_fetched_by_signature_alone():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=PNG, headers={'Content-Type': 'image/png'})

    content = await client_answering(handler).fetch_kept(IMAGE_ID)

    (request,) = seen
    path = f'/api/v1/asset/service/trpg/images/{IMAGE_ID}/kept'
    assert (request.method, request.url.path) == ('GET', path)
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', path, b'', time.time())
    assert 'Authorization' not in request.headers
    assert content == ImageContent(data=PNG, mime_type='image/png')


async def test_an_image_is_discarded_with_the_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    await client_answering(handler).discard_image(TOKEN, IMAGE_ID)

    (request,) = seen
    assert (request.method, request.url.path) == ('DELETE', f'/api/v1/asset/service/trpg/images/{IMAGE_ID}')
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'


async def test_a_missing_kept_image_is_not_found():
    client = client_answering(lambda request: answer(404, {'detail': '없다'}))

    with pytest.raises(AssetNotFoundError):
        await client.fetch_kept(IMAGE_ID)


@pytest.mark.parametrize(
    'response',
    [
        httpx.Response(500),
        httpx.Response(401),
        httpx.Response(200, content=b'{}', headers={'Content-Type': 'application/json'}),
        httpx.Response(200, content=b'', headers={'Content-Type': 'image/png'}),
    ],
)
async def test_an_unusable_kept_answer_is_unavailable(response: httpx.Response):
    client = client_answering(lambda request: response)

    with pytest.raises(AssetUnavailableError):
        await client.fetch_kept(IMAGE_ID)


@pytest.mark.parametrize('response', [httpx.Response(500), httpx.Response(200), httpx.Response(201, content=b'{}')])
async def test_an_unusable_keep_answer_is_unavailable(response: httpx.Response):
    client = client_answering(lambda request: response)

    with pytest.raises(AssetUnavailableError):
        await client.keep_image(TOKEN, PNG)


async def test_an_unreachable_server_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('닿지 못했다')

    with pytest.raises(AssetUnavailableError):
        await client_answering(handler).keep_image(TOKEN, PNG)


async def test_without_an_address_nothing_is_sent():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    with pytest.raises(AssetUnavailableError):
        await client_answering(handler, base_url='').fetch_kept(IMAGE_ID)
    assert seen == []


@pytest.mark.parametrize('secret', ['', 'short-secret'])
def test_an_address_without_a_long_secret_does_not_start(secret: str):
    with pytest.raises(ValidationError, match='ASSET_SECRET'):
        make_test_settings(asset_url=BASE_URL, asset_secret=secret)


def test_an_address_with_a_long_secret_starts():
    settings = make_test_settings(asset_url=BASE_URL, asset_secret=SECRET)

    assert settings.asset_url == BASE_URL
    assert SECRET not in repr(settings)
