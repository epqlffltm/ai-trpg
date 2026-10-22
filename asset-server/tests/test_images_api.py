# asset-server/tests/test_images_api.py

"""
그림 API(app/images/router.py, app/images/service.py)를 검증한다. 그림을 여는 것은 실제 프로세스이고,
저장소는 가짜(tests/images.py)다. 실제 저장소와 nginx 를 거친 내주기는 스택 시험이 본다.

보는 것.
  - 올리기: 201 과 그림의 행(형식, 크기, 너비와 높이, 내주는 주소). 저장소에는 다시 인코딩한 바이트와 형식이 들어간다
  - 형식은 파일의 머리로 본다. 요청의 Content-Type 은 보지 않는다
  - 거절: 로그인이 없으면 401(본문을 읽기 전에), 받지 않는 형식은 415, 열 수 없는 그림은 422, 상한을 넘으면 413,
    저장소를 쓸 수 없으면 503. 거절되면 행이 남지 않는다
  - 내주기: 주인이면 본문 없이 200 과 X-Accel-Redirect, X-Image-Source. 남, 토큰 없음, 없는 그림은 같은 404 다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import TEST_USER_ID, SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.images.models import Image
from app.images.store import UnconfiguredImageStore
from app.main import API_PREFIX
from tests.images import STORE_BUCKET, STORE_ORIGIN, FakeImageStore, jpeg_bytes, opened, png_bytes

pytestmark = pytest.mark.usefixtures('clean_tables')

IMAGES_URL = f'{API_PREFIX}/images'
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NOT_FOUND = {'detail': '찾을 수 없습니다.'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, TEST_USER_ID)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER)


@pytest.fixture
def store(app: FastAPI) -> FakeImageStore:
    """앱에 꽂은 가짜 저장소."""
    fake = FakeImageStore()
    app.state.image_store = fake
    return fake


async def upload(client: AsyncClient, headers: dict, data: bytes, content_type: str = 'image/png'):
    return await client.post(IMAGES_URL, content=data, headers={**headers, 'Content-Type': content_type})


async def image_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Image))


# --- 올리기 ---


async def test_an_upload_stores_the_encoded_image(client: AsyncClient, mine: dict, store: FakeImageStore):
    response = await upload(client, mine, png_bytes((7, 5)) + b'TRAILING')

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    (key,) = store.objects
    stored = store.objects[key]
    assert body['id'] == key
    assert (body['format'], body['width'], body['height']) == ('png', 7, 5)
    assert body['byte_size'] == len(stored.data)
    assert body['url'] == f'{IMAGES_URL}/{key}'
    assert stored.content_type == 'image/png'
    assert b'TRAILING' not in stored.data
    assert opened(stored.data).size == (7, 5)


async def test_the_row_belongs_to_the_uploader(
    client: AsyncClient, mine: dict, store: FakeImageStore, session: AsyncSession
):
    response = await upload(client, mine, jpeg_bytes((4, 2), orientation=6))

    image = await session.get(Image, uuid.UUID(response.json()['id']))
    # 방향을 적용한 뒤의 크기다
    assert (image.owner_id, image.format, image.width, image.height) == (TEST_USER_ID, 'jpeg', 2, 4)


async def test_the_format_comes_from_the_file_not_the_content_type(
    client: AsyncClient, mine: dict, store: FakeImageStore
):
    response = await upload(client, mine, jpeg_bytes(), content_type='image/png')

    assert response.json()['format'] == 'jpeg'
    assert next(iter(store.objects.values())).content_type == 'image/jpeg'


# --- 거절 ---


async def test_an_upload_needs_a_login(client: AsyncClient, store: FakeImageStore):
    response = await upload(client, {}, png_bytes())

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert store.objects == {}


@pytest.mark.parametrize(
    ('data', 'status_code', 'code'),
    [
        (b'GIF89a' + b'\x00' * 32, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 'image_format'),
        (b'', status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 'image_format'),
        (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64, status.HTTP_422_UNPROCESSABLE_CONTENT, 'image_unreadable'),
    ],
    ids=['gif', 'empty', 'broken-png'],
)
async def test_refused_files_leave_nothing(
    client: AsyncClient,
    mine: dict,
    store: FakeImageStore,
    session: AsyncSession,
    data: bytes,
    status_code: int,
    code: str,
):
    response = await upload(client, mine, data)

    assert (response.status_code, response.json()['code']) == (status_code, code)
    assert (store.objects, await image_count(session)) == ({}, 0)


async def test_a_file_over_the_limit_is_413(app: FastAPI, client: AsyncClient, mine: dict, store: FakeImageStore):
    app.state.settings = app.state.settings.model_copy(update={'image_max_bytes': 1024})

    over = await upload(client, mine, png_bytes((300, 300), color=(1, 2, 3)) + b'x' * 1024)
    under = await upload(client, mine, png_bytes())

    assert over.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert under.status_code == status.HTTP_201_CREATED


async def test_a_broken_store_is_503_and_leaves_no_row(
    client: AsyncClient, mine: dict, store: FakeImageStore, session: AsyncSession
):
    store.broken = True

    response = await upload(client, mine, png_bytes())

    assert (response.status_code, response.json()['code']) == (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        'image_store_unavailable',
    )
    assert await image_count(session) == 0


async def test_a_server_without_a_store_is_503(app: FastAPI, client: AsyncClient, mine: dict):
    app.state.image_store = UnconfiguredImageStore()

    response = await upload(client, mine, png_bytes())

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- 내주기 ---


async def uploaded(client: AsyncClient, headers: dict) -> str:
    response = await upload(client, headers, png_bytes())
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def test_the_owner_gets_the_redirect_headers(client: AsyncClient, mine: dict, store: FakeImageStore):
    image_id = await uploaded(client, mine)

    response = await client.get(f'{IMAGES_URL}/{image_id}', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b''
    assert response.headers['X-Accel-Redirect'] == f'/_images/{image_id}'
    assert response.headers['X-Image-Source'].startswith(f'{STORE_ORIGIN}/{STORE_BUCKET}/{image_id}?')


@pytest.mark.parametrize('who', ['theirs', 'nobody'])
async def test_others_and_strangers_get_404(
    client: AsyncClient, mine: dict, theirs: dict, store: FakeImageStore, who: str
):
    image_id = await uploaded(client, mine)

    response = await client.get(f'{IMAGES_URL}/{image_id}', headers=theirs if who == 'theirs' else {})

    assert (response.status_code, response.json()) == (status.HTTP_404_NOT_FOUND, NOT_FOUND)
    assert 'X-Accel-Redirect' not in response.headers


async def test_a_missing_image_is_404(client: AsyncClient, mine: dict, store: FakeImageStore):
    response = await client.get(f'{IMAGES_URL}/{uuid.uuid4()}', headers=mine)

    assert (response.status_code, response.json()) == (status.HTTP_404_NOT_FOUND, NOT_FOUND)


async def test_serving_without_a_store_is_503(app: FastAPI, client: AsyncClient, mine: dict, store: FakeImageStore):
    image_id = await uploaded(client, mine)
    store.broken = True

    response = await client.get(f'{IMAGES_URL}/{image_id}', headers=mine)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
