# asset-server/tests/test_supply_worlds.py

"""
게시한 세계관의 판을 story 서버에 내주는 주소(app/worlds/supply.py)를 검증한다.
서명은 tests/test_service_auth.py 가 본다.

보는 것.
  - 마지막 판의 번호와 문서를 내준다. 다시 게시하면 번호가 오른다
  - 쓸 수 있는 사람: 주인(비공개여도), 그리고 공개 세계관의 판의 등급을 볼 수 있는 사람
  - 쓸 수 없으면 404 다(남의 비공개, 볼 수 없는 등급, 게시한 적이 없는 것, 없는 것)
  - 주인인데 등급을 쓸 수 없으면 403 adult_content_required 다
  - 번호만 묻는 길도 같은 규칙이다. 서명이 틀리면 401 이다
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import FakeAuthServer, SigningKey
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from tests.conftest import make_client, make_test_settings
from tests.signing import signed_get
from tests.worlds import OTHER, OWNER, WORLDS_URL, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
BOTH_PATHS = ['/latest', '/latest/number']


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def player(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False)


@pytest.fixture
def adult(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False, adult=True)


async def published(client: AsyncClient, headers: dict, public: bool = False, **fields) -> dict:
    """게시한 세계관. public 이면 공개로 둔다."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    world = await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})
    if public:
        await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await publish(client, headers, world)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return world


async def test_the_owner_takes_the_latest_version(client: AsyncClient, owner: dict):
    world = await published(client, owner)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'name': '겨울 학원'}, headers=owner)
    await publish(client, owner, world)

    copied = await signed_get(client, f'/worlds/{world["id"]}/latest', owner)
    number = await signed_get(client, f'/worlds/{world["id"]}/latest/number', owner)

    assert copied.status_code == status.HTTP_200_OK, copied.text
    body = copied.json()
    assert (body['id'], body['version'], body['rating'], body['document']['name']) == (
        world['id'],
        2,
        'all',
        '겨울 학원',
    )
    assert number.json() == {'id': world['id'], 'version': 2}


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_someone_else_takes_only_a_public_world(client: AsyncClient, owner: dict, player: dict, suffix: str):
    private = await published(client, owner)
    public = await published(client, owner, public=True, name='공개')

    hidden = await signed_get(client, f'/worlds/{private["id"]}{suffix}', player)
    shown = await signed_get(client, f'/worlds/{public["id"]}{suffix}', player)

    assert (hidden.status_code, shown.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_an_adult_world_goes_only_to_adults(
    client: AsyncClient, owner: dict, player: dict, adult: dict, suffix: str
):
    world = await published(client, owner, public=True, rating='adult')

    responses = [await signed_get(client, f'/worlds/{world["id"]}{suffix}', headers) for headers in (player, adult)]

    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND, status.HTTP_200_OK]


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_unpublished_and_missing_worlds_are_not_there(client: AsyncClient, owner: dict, suffix: str):
    draft = await create_world(client, owner, {'name': '초안'})

    responses = [
        await signed_get(client, f'/worlds/{draft["id"]}{suffix}', owner),
        await signed_get(client, f'/worlds/{NO_SUCH_ID}{suffix}', owner),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * 2


@pytest.fixture
async def open_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """누구나 세계관을 만드는 앱(3단계)."""
    app = create_app(
        make_test_settings(characters_for_everyone=True), http_client=auth_server.make_client(), engine=engine
    )
    yield app
    await app.state.http_client.aclose()


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_an_owner_who_lost_adult_content_is_told_why(open_app: FastAPI, player: dict, adult: dict, suffix: str):
    async with make_client(open_app) as client:
        world = await published(client, adult, rating='adult')

        response = await signed_get(client, f'/worlds/{world["id"]}{suffix}', player)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['code'] == 'adult_content_required'


async def test_a_bad_signature_is_refused(client: AsyncClient, owner: dict):
    world = await published(client, owner)

    response = await signed_get(client, f'/worlds/{world["id"]}/latest', owner, secret='x' * 40)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
