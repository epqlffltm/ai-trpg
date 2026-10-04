# game-server/tests/test_listings_api.py

"""
시나리오의 공개와 소개 페이지를 검증한다.

두 부류의 사람이 쓴다.
  - 제작자: 소개 페이지(한줄소개, 소개글, 장르, 태그)를 고치고, 공개할 판을 하나 고른다.
  - 다른 사용자: 공개된 시나리오의 목록과 상세를 본다.

보는 것은 셋이다.
  - 소개 페이지는 판과 따로 고친다. 공개할 판은 시나리오마다 하나다.
  - 남에게는 공개된 것만, 정해 둔 칸만 보인다. GM 전용 글은 나가지 않는다.
  - 성인용은 지금 누구에게도 목록에 보이지 않는다(성인 인증이 아직 없다).
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType, Scenario, ScenarioVersion
from app.listings.models import LISTING_MAX_GENRES, LISTING_MAX_TAGS, TAG_MAX_LENGTH, TAGLINE_MAX_LENGTH, Listing
from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LISTINGS_URL = f'{API_PREFIX}/listings'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
TITLE = '17개 행성의 추격전'
OPENING = '사이렌이 울린다. 뒤를 돌아보니 마법소년 차림의 드워프가 망치를 들고 쫓아오고 있다.'
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
TAGLINE = '바이크, 엘프, 그리고 17건의 사형 선고'
DESCRIPTION = '실연당한 악역영애와 함께 달린다. 뒤는 돌아보지 않는 편이 좋다.'
GENRES = ['sf', 'comedy']
TAGS = ['추격전', '폭주족', '바이크']


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 토큰이 실린 머리말."""
    return bearer(signing_key, SOMEONE_ELSE)


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


def listing_url(scenario: dict) -> str:
    """제작자가 쓰는, 시나리오의 공개 정보 주소."""
    return f'{SCENARIOS_URL}/{scenario["id"]}/listing'


async def create_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """게시할 조건을 갖춘 시나리오를 만든다. 룰북이 붙어 있고 스타팅이 하나 있다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {'title': TITLE, 'rulebook_id': rulebook.json()['id'], 'openings': [OPENING]}
    body.update(fields)
    response = await client.post(SCENARIOS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish_version(client: AsyncClient, headers: dict[str, str], scenario: dict, note: str = '') -> int:
    """시나리오를 게시해 새 판을 내고, 그 번호를 돌려준다."""
    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={'note': note}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['number']


async def write_page(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields) -> dict:
    """소개 페이지를 쓴다. 공개할 조건(한줄소개, 장르)을 갖춘 내용이 기본이다."""
    body = {'tagline': TAGLINE, 'genres': GENRES}
    body.update(fields)
    response = await client.patch(listing_url(scenario), json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def make_public(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """시나리오를 만들고, 게시하고, 소개 페이지를 쓰고, 공개까지 한다. 시나리오를 돌려준다."""
    page = {key: fields.pop(key) for key in ('tagline', 'description', 'genres', 'tags') if key in fields}
    scenario = await create_scenario(client, headers, **fields)
    number = await publish_version(client, headers, scenario)
    await write_page(client, headers, scenario, **page)
    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': number}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return scenario


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'url'),
    [
        ('GET', f'{SCENARIOS_URL}/11111111-2222-4333-8444-555555555555/listing'),
        ('PATCH', f'{SCENARIOS_URL}/11111111-2222-4333-8444-555555555555/listing'),
        ('PUT', f'{SCENARIOS_URL}/11111111-2222-4333-8444-555555555555/listing/publication'),
        ('GET', LISTINGS_URL),
        ('GET', f'{LISTINGS_URL}/11111111-2222-4333-8444-555555555555'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, url: str):
    response = await client.request(method, url, json={})

    # 공개된 것을 보는 데도 로그인이 필요하다
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 소개 페이지 ---


async def test_a_scenario_starts_with_an_empty_page(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)

    response = await client.get(listing_url(scenario), headers=my_headers)

    # 아직 쓰지 않았어도 404 가 아니다. 화면이 빈 양식을 보여 줄 수 있다
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'scenario_id': scenario['id'],
        'tagline': '',
        'description': '',
        'genres': [],
        'tags': [],
        'version': None,
        'rating': None,
        'published_at': None,
        'updated_at': None,
    }


async def test_writes_the_page(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)

    page = await write_page(client, my_headers, scenario, description=DESCRIPTION, tags=TAGS)

    assert page['tagline'] == TAGLINE
    assert page['description'] == DESCRIPTION
    assert page['genres'] == GENRES
    assert page['tags'] == TAGS
    # 소개 페이지를 쓰는 것과 공개하는 것은 따로다
    assert page['version'] is None
    assert (await client.get(listing_url(scenario), headers=my_headers)).json() == page


async def test_updates_only_the_fields_that_were_sent(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario, description=DESCRIPTION, tags=TAGS)

    response = await client.patch(
        listing_url(scenario), json={'tagline': '새 한줄소개', 'tags': None}, headers=my_headers
    )

    page = response.json()
    assert page['tagline'] == '새 한줄소개'
    # 보내지 않은 칸과 null 로 보낸 칸은 그대로다
    assert page['description'] == DESCRIPTION
    assert page['genres'] == GENRES
    assert page['tags'] == TAGS


async def test_an_empty_list_clears_genres_and_tags(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario, tags=TAGS)

    response = await client.patch(listing_url(scenario), json={'genres': [], 'tags': []}, headers=my_headers)

    assert response.json()['genres'] == []
    assert response.json()['tags'] == []


async def test_tags_and_the_tagline_are_trimmed(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)

    page = await write_page(client, my_headers, scenario, tagline='  한줄소개  ', tags=['  추격전 ', '바이크'])

    assert page['tagline'] == '한줄소개'
    assert page['tags'] == ['추격전', '바이크']


async def test_accepts_the_most_genres_and_tags_allowed(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)
    genres = ['fantasy', 'wuxia', 'for_men'][:LISTING_MAX_GENRES]
    tags = [f'태그{number}' for number in range(LISTING_MAX_TAGS)]

    page = await write_page(client, my_headers, scenario, genres=genres, tags=tags)

    assert page['genres'] == genres
    assert page['tags'] == tags


@pytest.mark.parametrize(
    'body',
    [
        {'tagline': '가' * (TAGLINE_MAX_LENGTH + 1)},
        {'description': '가' * 5001},
        # 장르는 정해진 목록에서만 고른다
        {'genres': ['없는장르']},
        {'genres': ['fantasy', 'wuxia', 'sf', 'horror'][: LISTING_MAX_GENRES + 1]},
        {'genres': ['sf', 'sf']},
        {'genres': 'sf'},
        # 성인용은 장르가 아니다. 시나리오의 등급에서 온다
        {'genres': ['adult']},
        {'tags': [f'태그{number}' for number in range(LISTING_MAX_TAGS + 1)]},
        {'tags': ['가' * (TAG_MAX_LENGTH + 1)]},
        {'tags': ['   ']},
        {'tags': ['추격전', '추격전']},
        # 대소문자만 다른 것도 같은 태그다
        {'tags': ['Bike', 'bike']},
        # 앞뒤 공백을 떼면 같아진다
        {'tags': ['추격전', ' 추격전 ']},
        # 공개할 판과 등급은 여기서 정하지 않는다
        {'version': 1},
        {'rating': 'adult'},
        {'title': '바꿈'},
    ],
)
async def test_rejects_a_bad_page(client: AsyncClient, my_headers: dict[str, str], body: dict):
    scenario = await create_scenario(client, my_headers)

    response = await client.patch(listing_url(scenario), json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(listing_url(scenario), headers=my_headers)).json()['updated_at'] is None


async def test_someone_elses_page_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_scenario(client, their_headers)
    await publish_version(client, their_headers, theirs)
    await write_page(client, their_headers, theirs)

    read = await client.get(listing_url(theirs), headers=my_headers)
    update = await client.patch(listing_url(theirs), json={'tagline': '빼앗음'}, headers=my_headers)
    publish = await client.put(f'{listing_url(theirs)}/publication', json={'version': 1}, headers=my_headers)

    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert update.status_code == status.HTTP_404_NOT_FOUND
    assert publish.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(listing_url(theirs), headers=their_headers)).json()['tagline'] == TAGLINE


async def test_the_page_of_a_deleted_scenario_cannot_be_reached(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)
    await client.delete(f'{SCENARIOS_URL}/{scenario["id"]}', headers=my_headers)

    response = await client.get(listing_url(scenario), headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- 공개할 판 고르기 ---


async def test_makes_a_version_public(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_scenario(client, my_headers)
    await publish_version(client, my_headers, scenario)
    await write_page(client, my_headers, scenario)

    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    page = response.json()
    assert page['version'] == 1
    assert page['rating'] == 'all'
    assert page['published_at'] is not None


async def test_a_scenario_has_one_public_version(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers)
    await publish_version(client, my_headers, scenario, note='둘째 판')

    # 새 판을 냈다고 공개 판이 바뀌지 않는다. 제작자가 직접 바꿔야 한다
    before = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=my_headers)).json()
    await client.put(f'{listing_url(scenario)}/publication', json={'version': 2}, headers=my_headers)
    after = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=my_headers)).json()

    assert (before['version'], before['version_note']) == (1, '')
    assert (after['version'], after['version_note']) == (2, '둘째 판')
    # 목록에는 여전히 하나만 나온다
    assert (await client.get(LISTINGS_URL, headers=my_headers)).json()['total'] == 1


async def test_an_older_version_can_be_made_public_again(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers)
    await publish_version(client, my_headers, scenario)
    await client.put(f'{listing_url(scenario)}/publication', json={'version': 2}, headers=my_headers)

    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    assert response.json()['version'] == 1


async def test_taking_it_down_keeps_the_page(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers, tags=TAGS)

    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': None}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    page = response.json()
    assert page['version'] is None
    assert page['rating'] is None
    assert page['published_at'] is None
    # 소개 페이지의 글은 남는다. 다시 공개할 때 그대로 쓴다
    assert page['tagline'] == TAGLINE
    assert page['tags'] == TAGS


@pytest.mark.parametrize(
    ('page', 'problems'),
    [
        ({}, ['tagline_empty', 'genre_missing']),
        ({'tagline': TAGLINE}, ['genre_missing']),
        ({'genres': GENRES}, ['tagline_empty']),
        ({'tagline': '   ', 'genres': GENRES}, ['tagline_empty']),
    ],
)
async def test_a_page_that_is_not_ready_cannot_go_public(
    client: AsyncClient, my_headers: dict[str, str], page: dict, problems: list[str]
):
    scenario = await create_scenario(client, my_headers)
    await publish_version(client, my_headers, scenario)
    await client.patch(listing_url(scenario), json=page, headers=my_headers)

    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    # 못 갖춘 조건을 한 번에 전부 알려 준다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == problems
    assert (await client.get(LISTINGS_URL, headers=my_headers)).json()['total'] == 0


async def test_a_public_page_cannot_be_emptied(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers)

    response = await client.patch(listing_url(scenario), json={'tagline': '', 'genres': []}, headers=my_headers)

    # 공개 중인 페이지는 공개할 조건을 계속 갖춰야 한다. 비우려면 공개를 먼저 내린다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['tagline_empty', 'genre_missing']
    assert (await client.get(listing_url(scenario), headers=my_headers)).json()['tagline'] == TAGLINE


async def test_a_public_page_can_be_edited_without_a_new_version(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers)

    await client.patch(listing_url(scenario), json={'tagline': '고친 한줄소개', 'tags': ['새태그']}, headers=my_headers)

    public = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=my_headers)).json()
    assert public['tagline'] == '고친 한줄소개'
    assert public['tags'] == ['새태그']
    assert public['version'] == 1


async def test_only_a_version_of_this_scenario_can_go_public(client: AsyncClient, my_headers: dict[str, str]):
    other = await create_scenario(client, my_headers)
    await publish_version(client, my_headers, other)
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)

    # 이 시나리오에는 판이 없다. 다른 시나리오의 1번 판이 딸려 오지 않는다
    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize('body', [{}, {'version': 0}, {'version': 'latest'}, {'version': 1, 'rating': 'all'}])
async def test_rejects_a_bad_publication(client: AsyncClient, my_headers: dict[str, str], body: dict):
    scenario = await create_scenario(client, my_headers)
    await publish_version(client, my_headers, scenario)
    await write_page(client, my_headers, scenario)

    response = await client.put(f'{listing_url(scenario)}/publication', json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 공개된 것을 본다 ---


async def test_others_see_a_public_scenario(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    scenario = await make_public(client, my_headers, description=DESCRIPTION, tags=TAGS)

    response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=their_headers)

    assert response.status_code == status.HTTP_200_OK
    public = response.json()
    published_at = public.pop('published_at')
    assert published_at is not None
    assert public == {
        'scenario_id': scenario['id'],
        'creator_id': str(ME),
        'title': TITLE,
        'tagline': TAGLINE,
        'description': DESCRIPTION,
        'genres': GENRES,
        'tags': TAGS,
        'rating': 'all',
        'version': 1,
        'version_note': '',
    }
    # 판의 굳힌 내용은 나가지 않는다
    assert GM_GUIDE not in response.text
    assert OPENING not in response.text


async def test_the_list_shows_only_public_scenarios(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    public = await make_public(client, my_headers)
    # 판을 냈지만 공개하지 않은 것
    published_only = await create_scenario(client, my_headers, title='게시만 한 시나리오')
    await publish_version(client, my_headers, published_only)
    await write_page(client, my_headers, published_only)
    # 초안뿐인 것
    await create_scenario(client, my_headers, title='초안')

    response = await client.get(LISTINGS_URL, headers=their_headers)

    body = response.json()
    assert [item['scenario_id'] for item in body['items']] == [public['id']]
    assert body['total'] == 1
    hidden = await client.get(f'{LISTINGS_URL}/{published_only["id"]}', headers=their_headers)
    assert hidden.status_code == status.HTTP_404_NOT_FOUND


async def test_a_scenario_that_was_taken_down_or_deleted_disappears(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    taken_down = await make_public(client, my_headers, title='내린 시나리오')
    deleted = await make_public(client, my_headers, title='지운 시나리오')
    await client.put(f'{listing_url(taken_down)}/publication', json={'version': None}, headers=my_headers)
    await client.delete(f'{SCENARIOS_URL}/{deleted["id"]}', headers=my_headers)

    listed = await client.get(LISTINGS_URL, headers=their_headers)

    assert listed.json() == {'items': [], 'total': 0}
    for scenario in (taken_down, deleted):
        response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=their_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_lists_the_most_recently_published_first(client: AsyncClient, my_headers: dict[str, str]):
    first = await make_public(client, my_headers, title='첫째')
    second = await make_public(client, my_headers, title='둘째')
    third = await make_public(client, my_headers, title='셋째')

    page = (await client.get(LISTINGS_URL, params={'limit': 2}, headers=my_headers)).json()
    rest = (await client.get(LISTINGS_URL, params={'limit': 2, 'offset': 2}, headers=my_headers)).json()

    assert [item['scenario_id'] for item in page['items']] == [third['id'], second['id']]
    assert [item['scenario_id'] for item in rest['items']] == [first['id']]
    assert page['total'] == rest['total'] == 3


async def test_filters_by_genre_and_tag(client: AsyncClient, my_headers: dict[str, str]):
    chase = await make_public(client, my_headers, title='추격전', genres=['sf', 'comedy'], tags=['바이크'])
    ghost = await make_public(client, my_headers, title='귀신', genres=['horror'], tags=['폐가', '바이크'])
    sword = await make_public(client, my_headers, title='검객', genres=['wuxia', 'comedy'], tags=['복수'])

    async def ids(**params) -> set[str]:
        response = await client.get(LISTINGS_URL, params=params, headers=my_headers)
        assert response.json()['total'] == len(response.json()['items'])
        return {item['scenario_id'] for item in response.json()['items']}

    assert await ids(genre='comedy') == {chase['id'], sword['id']}
    assert await ids(genre='horror') == {ghost['id']}
    assert await ids(tag='바이크') == {chase['id'], ghost['id']}
    # 둘 다 주면 둘 다 맞는 것만 나온다
    assert await ids(genre='comedy', tag='바이크') == {chase['id']}
    assert await ids(genre='romance') == set()
    assert await ids(tag='없는태그') == set()


@pytest.mark.parametrize(
    'params', [{'genre': '없는장르'}, {'tag': ''}, {'tag': '가' * (TAG_MAX_LENGTH + 1)}, {'limit': 0}]
)
async def test_rejects_a_bad_filter(client: AsyncClient, my_headers: dict[str, str], params: dict):
    response = await client.get(LISTINGS_URL, params=params, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_title_follows_the_scenario(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await make_public(client, my_headers)

    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'title': '바꾼 제목'}, headers=my_headers)

    # 제목은 소개 페이지에 따로 두지 않는다. 시나리오의 제목을 고치면 바로 따라간다
    public = (await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=my_headers)).json()
    assert public['title'] == '바꾼 제목'


# --- 성인용 ---


async def test_an_adult_scenario_can_be_made_public_but_is_not_listed(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    scenario = await make_public(client, my_headers, rating='adult')

    mine = (await client.get(listing_url(scenario), headers=my_headers)).json()
    listed = await client.get(LISTINGS_URL, headers=their_headers)
    read = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=their_headers)
    read_by_owner = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=my_headers)

    # 제작자의 화면에는 공개 중이고 성인용이라고 나온다
    assert (mine['version'], mine['rating']) == (1, 'adult')
    # 성인 인증이 아직 없어서, 공개의 길에서는 누구에게도 보이지 않는다. 만든 사람에게도 그렇다
    assert listed.json() == {'items': [], 'total': 0}
    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert read_by_owner.status_code == status.HTTP_404_NOT_FOUND


async def test_the_rating_comes_from_the_public_version_not_the_draft(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    scenario = await make_public(client, my_headers, rating='adult')

    # 공개한 뒤에 초안의 등급을 전체 이용가로 내린다. 공개 중인 판은 여전히 성인용이다
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'rating': 'all'}, headers=my_headers)

    assert (await client.get(listing_url(scenario), headers=my_headers)).json()['rating'] == 'adult'
    assert (await client.get(LISTINGS_URL, headers=their_headers)).json()['total'] == 0

    # 전체 이용가로 새 판을 내고 그 판을 공개하면 그때 보인다
    number = await publish_version(client, my_headers, scenario)
    await client.put(f'{listing_url(scenario)}/publication', json={'version': number}, headers=my_headers)

    assert (await client.get(LISTINGS_URL, headers=their_headers)).json()['total'] == 1


async def test_a_version_in_the_old_format_can_be_made_public(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str], session: AsyncSession
):
    scenario = await create_scenario(client, my_headers)
    await write_page(client, my_headers, scenario)
    # 스타팅이 하나뿐이던 때(형식 1)에 굳힌 판. 공개할 때 등급을 이 문서에서 읽는다
    old = {'format': 1, 'title': TITLE, 'description': '', 'rating': 'all', 'opening': OPENING}
    old.update(rulebook={'id': str(ME), 'title': '룰북', 'gm_guide': GM_GUIDE}, world=None, lorebooks=[])
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=1, snapshot=old))
    await session.commit()

    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['rating'] == 'all'
    assert (await client.get(LISTINGS_URL, headers=their_headers)).json()['total'] == 1


# --- DB 의 마지막 방어선 ---


async def make_scenario(session: AsyncSession) -> uuid.UUID:
    """서비스를 거치지 않고 시나리오 하나를 저장한다."""
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.commit()
    return scenario.asset_id


async def test_the_database_rejects_too_many_genres(session: AsyncSession):
    scenario_id = await make_scenario(session)
    session.add(Listing(scenario_id=scenario_id, genres=['fantasy', 'wuxia', 'sf', 'horror']))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_too_many_tags(session: AsyncSession):
    scenario_id = await make_scenario(session)
    session.add(Listing(scenario_id=scenario_id, tags=[f'태그{number}' for number in range(LISTING_MAX_TAGS + 1)]))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_public_page_without_a_version(session: AsyncSession):
    scenario_id = await make_scenario(session)
    # 공개한 시각은 있는데 공개 중인 판이 없다
    session.add(Listing(scenario_id=scenario_id, published_at=datetime.now(UTC)))

    with pytest.raises(IntegrityError):
        await session.commit()
