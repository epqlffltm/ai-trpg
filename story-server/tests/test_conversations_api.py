# story-server/tests/test_conversations_api.py

"""
세션 API(app/conversations/)를 검증한다. 실제 DB(story_test)에서 돌고, asset 서버는 가짜다(tests/assets.py).

보는 것.
  - 시작: 세계관의 마지막 판을 고정한다(받은 칸 전부). 사용자의 토큰을 asset 서버에 넘긴다.
    판의 사본은 사람마다, 판마다 하나다. 다시 게시한 뒤 시작한 세션은 새 판을 쓰고, 앞의 세션은 그대로다
  - asset 서버의 답: 없음 404(world_not_found), 성인 확인 403, 닿지 못함 503(Retry-After). 아무것도 저장하지 않는다.
    asset 서버가 내준 판이어도 이 사람이 볼 수 없는 등급이면 404 다. 모르는 칸은 422 다
  - 목록: 내 것만, 볼 수 있는 등급만, 최근 것부터. 세계관으로 거른다. 쪽을 나눈다
  - 읽기: 남의 것, 볼 수 없는 등급, 없는 것은 404 다
  - 모든 주소가 로그인을 요구한다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld
from app.main import API_PREFIX
from app.ratings import Rating
from tests.assets import IMAGE_ID, FakeAsset, make_world, world_document

pytestmark = pytest.mark.usefixtures('clean_tables')

CONVERSATIONS_URL = f'{API_PREFIX}/conversations'
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


def bearer(signing_key: SigningKey, user_id: uuid.UUID = ME, adult: bool = False) -> dict[str, str]:
    claims = make_access_claims(sub=str(user_id))
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


def token_of(headers: dict[str, str]) -> str:
    return headers['Authorization'].removeprefix('Bearer ')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def my_adult(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, adult=True)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


async def start(client: AsyncClient, headers: dict, world_id: uuid.UUID) -> dict:
    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world_id)}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model))


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [('POST', CONVERSATIONS_URL), ('GET', CONVERSATIONS_URL), ('GET', f'{CONVERSATIONS_URL}/{NO_SUCH_ID}')],
)
async def test_every_address_needs_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, path, json={'world_id': NO_SUCH_ID})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 시작 ---


async def test_starting_fixes_the_latest_version(client: AsyncClient, asset: FakeAsset, mine: dict):
    world = asset.add_world(make_world(version=3))

    started = await start(client, mine, world.id)

    assert started['title'] == '여름 마을'
    assert started['world'] == {
        'id': str(world.id),
        'version': 3,
        'name': '여름 마을',
        'image_id': str(IMAGE_ID),
        'rating': 'all',
        'document': world_document(),
    }
    assert started['created_at'] == started['updated_at']


async def test_the_users_token_goes_to_the_asset_server(client: AsyncClient, asset: FakeAsset, mine: dict):
    world = asset.add_world(make_world())

    await start(client, mine, world.id)

    assert asset.calls == [(world.id, token_of(mine))]


async def test_one_copy_per_version_per_person(
    client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict, session: AsyncSession
):
    world = asset.add_world(make_world())
    await start(client, mine, world.id)
    await start(client, mine, world.id)
    await start(client, theirs, world.id)

    assert (await count(session, Conversation), await count(session, ImportedWorld)) == (3, 2)


async def test_a_new_version_goes_to_new_sessions_only(client: AsyncClient, asset: FakeAsset, mine: dict):
    world = asset.add_world(make_world())
    first = await start(client, mine, world.id)
    asset.add_world(make_world(world.id, version=2, name='가을 마을'))

    second = await start(client, mine, world.id)
    reread = (await client.get(f'{CONVERSATIONS_URL}/{first["id"]}', headers=mine)).json()

    assert (second['world']['version'], second['title']) == (2, '가을 마을')
    assert (reread['world']['version'], reread['title']) == (1, '여름 마을')


@pytest.mark.parametrize(
    ('setup', 'expected', 'code'),
    [
        ('missing', status.HTTP_404_NOT_FOUND, 'world_not_found'),
        ('adult_required', status.HTTP_403_FORBIDDEN, 'adult_content_required'),
    ],
)
async def test_what_the_asset_server_says_is_passed_on(
    client: AsyncClient, asset: FakeAsset, mine: dict, session: AsyncSession, setup: str, expected: int, code: str
):
    world_id = uuid.uuid4()
    if setup == 'adult_required':
        asset.adult_required.add(world_id)

    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world_id)}, headers=mine)

    assert (response.status_code, response.json()['code']) == (expected, code)
    assert await count(session, Conversation) == 0


async def test_unavailable_asks_to_try_again_later(
    client: AsyncClient, asset: FakeAsset, mine: dict, session: AsyncSession
):
    asset.down = True

    response = await client.post(CONVERSATIONS_URL, json={'world_id': NO_SUCH_ID}, headers=mine)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert (response.json()['code'], response.headers['Retry-After']) == ('asset_unavailable', '5')
    assert await count(session, ImportedWorld) == 0


async def test_an_adult_version_is_checked_here_too(
    client: AsyncClient, asset: FakeAsset, mine: dict, my_adult: dict, session: AsyncSession
):
    world = asset.add_world(make_world(rating=Rating.ADULT))

    refused = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id)}, headers=mine)
    allowed = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id)}, headers=my_adult)

    assert (refused.status_code, refused.json()['code']) == (status.HTTP_404_NOT_FOUND, 'world_not_found')
    assert allowed.status_code == status.HTTP_201_CREATED
    assert await count(session, Conversation) == 1


@pytest.mark.parametrize('body', [{}, {'world_id': 'nope'}, {'world_id': NO_SUCH_ID, 'owner_id': NO_SUCH_ID}])
async def test_bad_bodies_are_refused(client: AsyncClient, asset: FakeAsset, mine: dict, body: dict):
    response = await client.post(CONVERSATIONS_URL, json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert asset.calls == []


# --- 목록 ---


async def test_the_list_is_mine_and_newest_first(client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict):
    world = asset.add_world(make_world())
    older = await start(client, mine, world.id)
    newer = await start(client, mine, world.id)
    await start(client, theirs, world.id)

    page = (await client.get(CONVERSATIONS_URL, headers=mine)).json()

    assert page['total'] == 2
    assert [item['id'] for item in page['items']] == [newer['id'], older['id']]
    assert page['items'][0]['world'] == {
        'id': str(world.id),
        'version': 1,
        'name': '여름 마을',
        'image_id': str(IMAGE_ID),
        'rating': 'all',
    }


async def test_the_list_is_paged_and_filtered_by_world(client: AsyncClient, asset: FakeAsset, mine: dict):
    summer, autumn = asset.add_world(make_world()), asset.add_world(make_world(name='가을 마을'))
    for world in (summer, autumn, summer):
        await start(client, mine, world.id)

    first = (await client.get(CONVERSATIONS_URL, params={'limit': 2}, headers=mine)).json()
    second = (await client.get(CONVERSATIONS_URL, params={'limit': 2, 'offset': 2}, headers=mine)).json()
    summers = (await client.get(CONVERSATIONS_URL, params={'world_id': str(summer.id)}, headers=mine)).json()

    assert (first['total'], len(first['items']), len(second['items'])) == (3, 2, 1)
    assert summers['total'] == 2
    assert {item['world']['id'] for item in summers['items']} == {str(summer.id)}


async def test_unviewable_ones_are_not_listed(
    client: AsyncClient, asset: FakeAsset, signing_key: SigningKey, my_adult: dict
):
    adult = asset.add_world(make_world(rating=Rating.ADULT))
    await start(client, my_adult, adult.id)

    # 성인 확인을 잃은 뒤의 같은 사람
    lost = (await client.get(CONVERSATIONS_URL, headers=bearer(signing_key))).json()
    kept = (await client.get(CONVERSATIONS_URL, headers=my_adult)).json()

    assert (lost['total'], kept['total']) == (0, 1)


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 101}, {'offset': -1}, {'world_id': 'nope'}])
async def test_bad_list_parameters_are_refused(client: AsyncClient, mine: dict, params: dict):
    response = await client.get(CONVERSATIONS_URL, params=params, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 읽기 ---


async def test_reading_gives_the_same_as_starting(client: AsyncClient, asset: FakeAsset, mine: dict):
    started = await start(client, mine, asset.add_world(make_world()).id)

    response = await client.get(f'{CONVERSATIONS_URL}/{started["id"]}', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == started


async def test_others_unviewable_and_missing_are_404(
    client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict, my_adult: dict
):
    theirs_started = await start(client, theirs, asset.add_world(make_world()).id)
    adult_started = await start(client, my_adult, asset.add_world(make_world(rating=Rating.ADULT)).id)

    for conversation_id in (theirs_started['id'], adult_started['id'], NO_SUCH_ID):
        response = await client.get(f'{CONVERSATIONS_URL}/{conversation_id}', headers=mine)
        assert response.status_code == status.HTTP_404_NOT_FOUND
