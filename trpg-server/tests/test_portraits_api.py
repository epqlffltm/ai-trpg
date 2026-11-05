# trpg-server/tests/test_portraits_api.py

"""
제작자의 캐릭터 그림(#983)의 API 를 검증한다. asset 서버는 가짜다(tests/asset_server.py).

보는 것.
  - 올린 그림은 올린 사람의 토큰으로 asset 에 맡기고 기록한다. 목록에 최근 것부터 보이고, 바이트는 이 서버가 대신 내준다
  - 남의 그림은 목록에 없고 바이트도 404 다
  - asset 이 그림을 받지 않으면 그 까닭(형식, 열 수 없음)이고 기록하지 않는다
  - 본문이 상한을 넘으면 asset 을 부르지 않고 413 이다
  - 올릴 수 있는 수를 다 채우면 409 다
  - asset 이 죽었으면 503 이고 기록하지 않는다. asset 에서 사라진 그림은 404 다
  - 로그인해야 한다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.main import API_PREFIX
from app.portraits import service
from tests.asset_server import FakeAsset
from tests.test_round_closing import FRIEND, ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

URL = f'{API_PREFIX}/portraits'
PNG = b'\x89PNG portrait'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    """앱에 꽂은 가짜 asset 서버."""
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict[str, str], data: bytes = PNG) -> dict:
    response = await client.post(URL, content=data, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def listed(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.get(URL, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_an_uploaded_portrait_is_kept_for_the_uploader_and_passed_on(client: AsyncClient, me, asset):
    first = await upload(client, me, b'first')
    second = await upload(client, me, b'second')

    page = await listed(client, me)
    image = await client.get(f'{URL}/{first["id"]}/image', headers=me)

    assert [item['id'] for item in page['items']] == [second['id'], first['id']]
    assert page['total'] == 2
    assert asset.owners[uuid.UUID(first['id'])] == me['Authorization'].removeprefix('Bearer ')
    assert (image.status_code, image.content) == (status.HTTP_200_OK, b'first')
    assert image.headers['content-type'] == 'image/png'
    assert image.headers['cache-control'] == 'private, max-age=3600'


async def test_someone_elses_portrait_is_not_found(client: AsyncClient, me, friend, asset):
    mine = await upload(client, me)

    others = await listed(client, friend)
    image = await client.get(f'{URL}/{mine["id"]}/image', headers=friend)

    assert others == {'items': [], 'total': 0}
    assert (image.status_code, image.json()['code']) == (status.HTTP_404_NOT_FOUND, 'portrait_not_found')


@pytest.mark.parametrize(
    ('reason', 'status_code'),
    [
        ('image_format', status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
        ('image_unreadable', status.HTTP_422_UNPROCESSABLE_CONTENT),
    ],
)
async def test_an_image_the_asset_server_refuses_is_not_recorded(
    client: AsyncClient, me, asset, reason: str, status_code: int
):
    asset.rejecting = reason

    response = await client.post(URL, content=b'not an image', headers=me)

    assert (response.status_code, response.json()['code']) == (status_code, reason)
    assert (await listed(client, me))['total'] == 0


async def test_a_body_over_the_limit_never_reaches_the_asset_server(app: FastAPI, client: AsyncClient, me, asset):
    app.state.settings = app.state.settings.model_copy(update={'portrait_max_bytes': 4})

    response = await client.post(URL, content=b'12345', headers=me)

    assert (response.status_code, response.json()['code']) == (status.HTTP_413_CONTENT_TOO_LARGE, 'image_too_large')
    assert asset.kept == {}


async def test_a_full_shelf_refuses_more(client: AsyncClient, me, asset, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, 'PORTRAIT_MAX_PER_OWNER', 1)
    await upload(client, me)

    response = await client.post(URL, content=PNG, headers=me)

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'portrait_limit')
    assert len(asset.kept) == 1


async def test_a_dead_asset_server_records_nothing(client: AsyncClient, me, asset):
    asset.down = True

    response = await client.post(URL, content=PNG, headers=me)

    assert (response.status_code, response.json()['code']) == (status.HTTP_503_SERVICE_UNAVAILABLE, 'asset_unavailable')
    assert (await listed(client, me))['total'] == 0


async def test_a_portrait_lost_by_the_asset_server_is_not_found(client: AsyncClient, me, asset):
    mine = await upload(client, me)
    asset.kept.clear()

    image = await client.get(f'{URL}/{mine["id"]}/image', headers=me)

    assert (image.status_code, image.json()['code']) == (status.HTTP_404_NOT_FOUND, 'portrait_not_found')


@pytest.mark.usefixtures('asset')
async def test_portraits_need_a_login(client: AsyncClient):
    uploaded = await client.post(URL, content=PNG)
    page = await client.get(URL)

    assert (uploaded.status_code, page.status_code) == (status.HTTP_401_UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
