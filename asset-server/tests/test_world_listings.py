# asset-server/tests/test_world_listings.py

"""
공개 세계관의 목록과 소개(app/worlds/listings.py)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 공개이고 게시한 세계관만, 최근에 게시한 것부터 나온다. 마지막 판의 값이다(그 뒤에 고친 초안이 아니다)
  - 로그인하지 않아도 전체 이용가는 읽는다. 성인 등급은 성인 확인을 한 사람(과 운영자)만 본다
  - 볼 수 없는 것(비공개, 게시한 적이 없는 것, 볼 수 없는 등급, 없는 것)은 404 다. 틀린 토큰은 401 이다
  - 소개는 보여도 되는 것만이다: 보임 인물은 이름과 그림, 실루엣은 가리고, 숨김은 없다.
    이벤트와 엔딩의 조건은 없고 계정에 남는 엔딩의 수만 있다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.main import API_PREFIX
from app.search import SEARCH_MAX_LENGTH
from tests.worlds import OTHER, OWNER, WORLDS_URL, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

LISTINGS_URL = f'{API_PREFIX}/listings/worlds'
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def player(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False)


@pytest.fixture
def adult(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False, adult=True)


async def published(client: AsyncClient, headers: dict, public: bool = True, **fields) -> dict:
    """게시한 세계관. public 이면 공개로 둔다. 아리는 보임, 버는 실루엣(세계관의 기본)이다."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    world = await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})
    if public:
        await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await publish(client, headers, world)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return world


async def test_public_published_worlds_are_listed_newest_first(client: AsyncClient, owner: dict):
    first = await published(client, owner, name='첫 여름')
    second = await published(client, owner, name='두 번째 여름')
    await published(client, owner, public=False, name='비공개')
    # 공개로 두었지만 게시한 적이 없다
    draft = await create_world(client, owner, {'genre': 'romance', 'name': '게시 안 함'})
    await client.patch(f'{WORLDS_URL}/{draft["id"]}', json={'visibility': 'public'}, headers=owner)

    response = await client.get(LISTINGS_URL)

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert ([item['id'] for item in body['items']], body['total']) == ([second['id'], first['id']], 2)
    assert (body['items'][0]['name'], body['items'][0]['deadline_days'], body['items'][0]['version']) == (
        '두 번째 여름',
        30,
        1,
    )


async def test_the_listing_shows_the_published_version_not_the_draft(client: AsyncClient, owner: dict):
    world = await published(client, owner)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'name': '고치는 중'}, headers=owner)

    items = (await client.get(LISTINGS_URL)).json()['items']
    detail = (await client.get(f'{LISTINGS_URL}/{world["id"]}')).json()

    assert (items[0]['name'], detail['name']) == ('여름 학원', '여름 학원')


async def test_adult_worlds_are_seen_only_by_adults(client: AsyncClient, owner: dict, player: dict, adult: dict):
    world = await published(client, owner, rating='adult')
    url = f'{LISTINGS_URL}/{world["id"]}'

    assert (await client.get(LISTINGS_URL)).json()['total'] == 0
    assert (await client.get(LISTINGS_URL, headers=player)).json()['total'] == 0
    assert (await client.get(LISTINGS_URL, headers=adult)).json()['total'] == 1
    assert (await client.get(url)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(url, headers=adult)).status_code == status.HTTP_200_OK


async def test_worlds_that_cannot_be_seen_are_404(client: AsyncClient, owner: dict):
    private = await published(client, owner, public=False)

    for world_id in (private['id'], NO_SUCH_ID):
        response = await client.get(f'{LISTINGS_URL}/{world_id}')
        assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_wrong_token_is_401(client: AsyncClient):
    response = await client.get(LISTINGS_URL, headers={'Authorization': 'Bearer nope'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_intro_shows_only_what_may_be_seen(client: AsyncClient, owner: dict):
    world = await published(client, owner)

    detail = (await client.get(f'{LISTINGS_URL}/{world["id"]}')).json()

    # 소개는 게시할 때 거른 것이다
    assert detail['intro_html'] == '<p>여름 방학의 학원.</p>'
    assert (detail['tags'], detail['rating'], detail['deadline_days'], detail['after_ending']) == (
        ['학원'],
        'all',
        30,
        'end',
    )
    # 아리는 보임, 버는 실루엣(이름과 그림을 가린다)
    assert detail['cast'] == [
        {'id': 'ari', 'reveal': 'shown', 'name': '아리', 'image_id': None},
        {'id': 'beo', 'reveal': 'silhouette', 'name': None, 'image_id': None},
    ]
    # 계정에 남는 엔딩은 둘이다. 이벤트와 엔딩의 조건, 일정은 싣지 않는다
    assert detail['ending_count'] == 2
    assert not {'events', 'endings', 'document', 'places'} & detail.keys()


async def test_hidden_cast_members_are_left_out(client: AsyncClient, owner: dict):
    ari, beo = await character(client, owner, '아리'), await character(client, owner, '버')
    body = full_world(ari['id'], beo['id'])
    body['show'] = {**body['show'], 'reveal': 'hidden'}
    world = await create_world(client, owner, body)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=owner)
    assert (await publish(client, owner, world)).status_code == status.HTTP_201_CREATED

    detail = (await client.get(f'{LISTINGS_URL}/{world["id"]}')).json()

    assert [member['id'] for member in detail['cast']] == ['ari']


async def searched_ids(client: AsyncClient, q: str, headers: dict | None = None) -> list[str]:
    response = await client.get(LISTINGS_URL, params={'q': q}, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['total'] == len(response.json()['items'])
    return [item['id'] for item in response.json()['items']]


async def test_the_listing_searches_the_name_or_one_tag(client: AsyncClient, owner: dict):
    summer = await published(client, owner, name='첫 여름', tags=['학원'])
    winter = await published(client, owner, name='여름 없는 겨울', tags=['판타지'])

    assert await searched_ids(client, '여름') == [winter['id'], summer['id']]
    assert await searched_ids(client, '첫') == [summer['id']]
    assert await searched_ids(client, '#판타지') == [winter['id']]
    assert await searched_ids(client, '#여름') == []


async def test_the_search_still_hides_adult_worlds(client: AsyncClient, owner: dict, player: dict, adult: dict):
    world = await published(client, owner, name='밤의 여름', rating='adult')

    assert await searched_ids(client, '여름', player) == []
    assert await searched_ids(client, '여름', adult) == [world['id']]


@pytest.mark.parametrize('q', ['', '  ', '#', '가' * (SEARCH_MAX_LENGTH + 1)])
async def test_the_listing_rejects_a_bad_search(client: AsyncClient, q: str):
    response = await client.get(LISTINGS_URL, params={'q': q})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_an_unlisted_world_is_not_listed_but_opens_by_its_id(client: AsyncClient, owner: dict, player: dict):
    shown = await published(client, owner, name='보이는 여름')
    ari = await character(client, owner, '아리')
    beo = await character(client, owner, '버')
    hidden = await create_world(client, owner, {**full_world(ari['id'], beo['id']), 'name': '링크만 여름'})
    await client.patch(f'{WORLDS_URL}/{hidden["id"]}', json={'visibility': 'unlisted'}, headers=owner)
    assert (await publish(client, owner, hidden)).status_code == status.HTTP_201_CREATED

    page = (await client.get(LISTINGS_URL, headers=player)).json()
    opened = await client.get(f'{LISTINGS_URL}/{hidden["id"]}', headers=player)

    # 목록과 검색에는 없다(#993). 주소를 알면 소개가 열린다
    assert ([item['id'] for item in page['items']], page['total']) == ([shown['id']], 1)
    assert await searched_ids(client, '여름', player) == [shown['id']]
    assert (opened.status_code, opened.json()['name']) == (status.HTTP_200_OK, '링크만 여름')


async def test_world_listing_preferences(client: AsyncClient, owner: dict, adult: dict):
    day = await published(client, owner, name='낮의 여름', tags=['여성향'])
    await published(client, owner, name='밤의 여름', rating='adult')

    async def ids(**params) -> list[str]:
        response = await client.get(LISTINGS_URL, params=params, headers=adult)
        assert response.json()['total'] == len(response.json()['items'])
        return [item['id'] for item in response.json()['items']]

    # 성인 작품 숨김(#986)과 성향(#987)은 캐릭터의 목록과 같다
    assert len(await ids()) == 2
    assert await ids(hide_adult='true') == [day['id']]
    assert await ids(orientation='female') == [day['id']]
    assert await ids(orientation='male') == []
