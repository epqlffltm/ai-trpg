# asset-server/tests/test_image_supply.py

"""
다른 서버가 장면 그림을 맡기고 지우는 주소(app/images/supply.py, #983)를 검증한다.
그림을 여는 것은 실제 프로세스이고, 저장소는 가짜(tests/images.py)다.

보는 것.
  - 맡기기: 서명과 토큰이 맞으면 토큰의 주인의 그림으로 다시 인코딩해 올리고 201. 주인만 본다
  - 서명은 그림의 바이트까지 본다(바꾼 바이트는 401). 서명이 없으면 토큰이 있어도 401
  - 받지 않는 형식은 415, 상한을 넘으면 413. 거절되면 행이 남지 않는다
  - 지우기: 내 그림은 저장소와 행에서 지운다. 남의 것, 없는 것, 판에 쓰인 것은 그대로 두고 204
  - 바이트 내주기: 볼 수 있는 그림(내 것, 공개된 판에 쓰인 것)의 바이트와 형식. 남의 비공개 그림과 없는 그림은 404,
    저장소를 쓸 수 없으면 503
  - 맡긴 서버가 받기(kept): 맡긴 서버를 적고, 그 서버는 토큰 없이 서명만으로 받는다. 다른 서버가 맡긴 것, 사용자가
    올린 것, 없는 것은 404. 서명이 틀리면 401
"""

import time
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient, Response
from server_core.service_auth.signing import SIGNATURE_HEADER, sign
from server_core.testing.tokens import TEST_USER_ID, SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.images.models import Image
from app.main import API_PREFIX
from tests.images import FakeImageStore, opened, png_bytes
from tests.signing import TEST_SECRETS, service_path

pytestmark = pytest.mark.usefixtures('clean_tables')

OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    # 판에 쓰인 그림을 만들려고 캐릭터를 게시한다. 1~2단계에는 운영자만 캐릭터를 만든다
    claims = make_access_claims(sub=str(user_id))
    claims['roles'] = ['operator'] if user_id == TEST_USER_ID else []
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, TEST_USER_ID)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER)


@pytest.fixture
def store(app: FastAPI) -> FakeImageStore:
    fake = FakeImageStore()
    app.state.image_store = fake
    return fake


async def signed(
    client: AsyncClient,
    method: str,
    rest: str,
    headers: dict,
    body: bytes = b'',
    signed_body: bytes | None = None,
    caller: str = 'story',
) -> Response:
    """그 서버(기본 story)처럼 서명해 보낸다. signed_body 를 주면 그 바이트로 서명한다(바꿔치기한 본문)."""
    path = service_path(caller, rest)
    signature = sign(TEST_SECRETS[caller], int(time.time()), method, path, body if signed_body is None else signed_body)
    return await client.request(method, path, content=body, headers={**headers, SIGNATURE_HEADER: signature})


async def image_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Image))


async def test_a_kept_image_is_re_encoded_and_only_the_owner_sees_it(
    client: AsyncClient, session: AsyncSession, store: FakeImageStore, mine: dict, theirs: dict
):
    response = await signed(client, 'POST', '/images', mine, png_bytes((6, 4)) + b'TRAILING')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    stored = store.objects[body['id']]
    assert (body['format'], body['width'], body['height']) == ('png', 6, 4)
    assert b'TRAILING' not in stored.data and opened(stored.data).size == (6, 4)
    image = await session.get(Image, uuid.UUID(body['id']))
    assert image is not None and image.owner_id == TEST_USER_ID
    assert (await client.get(f'{API_PREFIX}/images/{body["id"]}', headers=mine)).status_code == status.HTTP_200_OK
    assert (await client.get(f'{API_PREFIX}/images/{body["id"]}', headers=theirs)).status_code == 404


async def test_the_signature_covers_the_image_bytes(
    client: AsyncClient, session: AsyncSession, store: FakeImageStore, mine: dict
):
    swapped = await signed(client, 'POST', '/images', mine, png_bytes((3, 3)), signed_body=png_bytes((2, 2)))
    unsigned = await client.post(service_path('story', '/images'), content=png_bytes(), headers=mine)

    assert (swapped.status_code, unsigned.status_code) == (status.HTTP_401_UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    assert await image_count(session) == 0


async def test_bad_images_are_refused_and_leave_nothing(
    app: FastAPI, client: AsyncClient, session: AsyncSession, store: FakeImageStore, mine: dict
):
    not_an_image = await signed(client, 'POST', '/images', mine, b'GIF89a' + b'\x00' * 20)
    app.state.settings = app.state.settings.model_copy(update={'image_max_bytes': 1024})
    too_large = await signed(client, 'POST', '/images', mine, png_bytes((300, 300)) + b'\x00' * 2048)

    assert not_an_image.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert too_large.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert await image_count(session) == 0 and not store.objects


async def test_discarding_removes_only_my_unused_image(
    client: AsyncClient, session: AsyncSession, store: FakeImageStore, mine: dict, theirs: dict
):
    kept = (await signed(client, 'POST', '/images', mine, png_bytes())).json()['id']
    used = (await signed(client, 'POST', '/images', mine, png_bytes())).json()['id']
    await publish_with_image(client, mine, used)

    by_someone_else = await signed(client, 'DELETE', f'/images/{kept}', theirs)
    still_there = kept in store.objects
    mine_gone = await signed(client, 'DELETE', f'/images/{kept}', mine)
    in_use = await signed(client, 'DELETE', f'/images/{used}', mine)
    missing = await signed(client, 'DELETE', f'/images/{uuid.uuid4()}', mine)

    assert [r.status_code for r in (by_someone_else, mine_gone, in_use, missing)] == [status.HTTP_204_NO_CONTENT] * 4
    assert still_there
    assert kept not in store.objects and await session.get(Image, uuid.UUID(kept)) is None
    session.expire_all()
    assert used in store.objects and await session.get(Image, uuid.UUID(used)) is not None


async def publish_with_image(client: AsyncClient, headers: dict, image_id: str, visibility: str = 'private') -> None:
    """그 그림을 대표 그림으로 단 캐릭터를 게시한다(그림이 판에 쓰인다)."""
    start = [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}]
    body = {'genre': 'romance', 'name': '세라', 'starts': start, 'image_id': image_id}
    made = await client.post(f'{API_PREFIX}/characters', json=body, headers=headers)
    assert made.status_code == status.HTTP_201_CREATED, made.text
    url = f'{API_PREFIX}/characters/{made.json()["id"]}'
    assert (await client.patch(url, json={'visibility': visibility}, headers=headers)).status_code == 200
    published = await client.post(f'{API_PREFIX}/characters/{made.json()["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text


async def test_the_bytes_of_a_viewable_image(client: AsyncClient, store: FakeImageStore, mine: dict, theirs: dict):
    private = (await signed(client, 'POST', '/images', mine, png_bytes((5, 5)))).json()['id']
    public = (await signed(client, 'POST', '/images', mine, png_bytes((4, 4)))).json()['id']
    await publish_with_image(client, mine, public, visibility='public')

    own = await signed(client, 'GET', f'/images/{private}/content', mine)
    shared = await signed(client, 'GET', f'/images/{public}/content', theirs)
    hidden = await signed(client, 'GET', f'/images/{private}/content', theirs)
    missing = await signed(client, 'GET', f'/images/{uuid.uuid4()}/content', mine)
    store.broken = True
    broken = await signed(client, 'GET', f'/images/{private}/content', mine)

    assert (own.status_code, own.headers['content-type']) == (status.HTTP_200_OK, 'image/png')
    assert own.content == store.objects[private].data and opened(own.content).size == (5, 5)
    assert shared.status_code == status.HTTP_200_OK and opened(shared.content).size == (4, 4)
    assert hidden.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert broken.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


async def test_the_keeping_server_reads_its_image_without_a_token(
    client: AsyncClient, session: AsyncSession, store: FakeImageStore, mine: dict
):
    kept = (await signed(client, 'POST', '/images', mine, png_bytes((5, 5)), caller='trpg')).json()['id']
    by_story = (await signed(client, 'POST', '/images', mine, png_bytes((4, 4)))).json()['id']
    uploaded = (await client.post(f'{API_PREFIX}/images', content=png_bytes((3, 3)), headers=mine)).json()['id']

    own = await signed(client, 'GET', f'/images/{kept}/kept', {}, caller='trpg')
    others = await signed(client, 'GET', f'/images/{by_story}/kept', {}, caller='trpg')
    from_user = await signed(client, 'GET', f'/images/{uploaded}/kept', {}, caller='trpg')
    missing = await signed(client, 'GET', f'/images/{uuid.uuid4()}/kept', {}, caller='trpg')
    unsigned = await client.get(service_path('trpg', f'/images/{kept}/kept'))
    wrong_server = await signed(client, 'GET', f'/images/{kept}/kept', {}, caller='story')

    assert (own.status_code, own.headers['content-type']) == (status.HTTP_200_OK, 'image/png')
    assert own.content == store.objects[kept].data
    assert others.status_code == from_user.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert wrong_server.status_code == status.HTTP_404_NOT_FOUND
    assert unsigned.status_code == status.HTTP_401_UNAUTHORIZED
    kept_rows = {str(row.id): row.kept_by for row in await session.scalars(select(Image))}
    assert kept_rows == {kept: 'trpg', by_story: 'story', uploaded: None}
