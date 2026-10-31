# asset-server/tests/test_worlds_api.py

"""
세계관의 초안 API(#591)를 검증한다. 실제 DB(asset_test)에서 돈다. 게시는 tests/test_world_publishing.py 가 본다.

보는 것.
  - 만들기: 이름만 있으면 된다. 시간대는 아침, 낮, 저녁, 밤이고 시작 시간대는 첫 시간대다. 보이기는 모두 보인다.
    처음에는 비공개다. 1~2단계에는 운영자만 만든다(403 operator_only). 성인 등급은 볼 수 있는 사람만이다
  - 고치기: 보낸 칸만 바뀐다. null 은 그림, 시작 장소와 시간대, 기한만 받는다. 공개로 두는 것은 운영자만이다
  - 남의 세계관은 읽고 고치고 지우지 못한다(404). 목록에는 내 것만 나온다
  - 칸의 검사(422): 시간대의 시각은 차례로 커지고 이름과 id 는 하나씩, 같은 캐릭터를 두 번 넣지 않는다,
    조건은 종류마다 쓰는 칸만 채운다, 선물의 규칙은 호감도를 바꾼다, 기한은 1~365 일, 보이기의 항목은 한 번씩
  - 인물은 자기 캐릭터만, 로어북은 자기 로어북만 가리킨다(422 character_not_owned, lorebook_not_owned)
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import FakeAuthServer, SigningKey
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from tests.conftest import make_client, make_test_settings
from tests.worlds import LOREBOOKS_URL, OTHER, OWNER, WORLDS_URL, bearer, character, create_world, member

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def other(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER)


@pytest.fixture
def plain(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False)


@pytest.fixture
async def open_client(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """누구나 세계관을 만드는 앱(3단계, CHARACTERS_FOR_EVERYONE)에 보내는 클라이언트."""
    app = create_app(
        make_test_settings(characters_for_everyone=True), http_client=auth_server.make_client(), engine=engine
    )
    async with make_client(app) as client:
        yield client
    await app.state.http_client.aclose()


# --- 만들기 ---


async def test_a_world_starts_with_the_default_slots_and_shows_everything(client: AsyncClient, owner: dict):
    made = await create_world(client, owner, {'genre': 'romance', 'name': '여름 학원'})

    assert [slot['id'] for slot in made['slots']] == ['morning', 'day', 'evening', 'night']
    assert [slot['start_hour'] for slot in made['slots']] == [7, 11, 17, 21]
    assert made['start_slot'] == 'morning'
    assert made['show'] == {'reveal': 'shown', 'map': 'shown', 'panel': ['intro', 'age', 'gender', 'affection']}
    assert (made['visibility'], made['after_ending'], made['deadline_days']) == ('private', 'end', None)
    assert (made['cast'], made['places'], made['latest_version']) == ([], [], None)


async def test_the_start_slot_can_be_any_slot(client: AsyncClient, owner: dict):
    slots = [{'id': 'am', 'name': '오전', 'start_hour': 6}, {'id': 'pm', 'name': '오후', 'start_hour': 12}]

    made = await create_world(client, owner, {'genre': 'romance', 'name': '둘', 'slots': slots, 'start_slot': 'pm'})

    assert (made['start_slot'], [slot['id'] for slot in made['slots']]) == ('pm', ['am', 'pm'])


async def test_only_operators_make_worlds_for_now(client: AsyncClient, plain: dict):
    response = await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '여름 학원'}, headers=plain)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['code'] == 'operator_only'


async def test_operators_and_adults_use_the_adult_rating(client: AsyncClient, owner: dict, signing_key: SigningKey):
    response = await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '밤', 'rating': 'adult'}, headers=owner)
    adult = bearer(signing_key, OWNER, adult=True)
    allowed = await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '밤', 'rating': 'adult'}, headers=adult)

    # 운영자는 성인 등급을 쓸 수 있다(app/ratings.py)
    assert (response.status_code, allowed.status_code) == (status.HTTP_201_CREATED, status.HTTP_201_CREATED)


async def test_a_plain_user_cannot_use_the_adult_rating(open_client: AsyncClient, plain: dict):
    response = await open_client.post(
        WORLDS_URL, json={'genre': 'romance', 'name': '밤', 'rating': 'adult'}, headers=plain
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# --- 읽기, 목록, 고치기, 지우기 ---


async def test_the_owner_lists_reads_updates_and_deletes(client: AsyncClient, owner: dict):
    made = await create_world(client, owner, {'genre': 'romance', 'name': '여름 학원', 'deadline_days': 30})
    url = f'{WORLDS_URL}/{made["id"]}'

    listed = await client.get(WORLDS_URL, headers=owner)
    changed = await client.patch(url, json={'name': '겨울 학원', 'deadline_days': None}, headers=owner)
    read = await client.get(url, headers=owner)
    deleted = await client.delete(url, headers=owner)

    assert [item['name'] for item in listed.json()['items']] == ['여름 학원']
    assert (changed.json()['name'], changed.json()['deadline_days']) == ('겨울 학원', None)
    assert read.json()['name'] == '겨울 학원'
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(url, headers=owner)).status_code == status.HTTP_404_NOT_FOUND


async def test_someone_elses_world_is_not_there(client: AsyncClient, owner: dict, other: dict):
    made = await create_world(client, owner, {'genre': 'romance', 'name': '여름 학원'})
    url = f'{WORLDS_URL}/{made["id"]}'

    responses = [
        await client.get(url, headers=other),
        await client.patch(url, json={'name': '빼앗기'}, headers=other),
        await client.delete(url, headers=other),
        await client.get(f'{url}/publish-check', headers=other),
        await client.post(f'{url}/versions', json={}, headers=other),
        await client.get(f'{url}/versions', headers=other),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * len(responses)
    assert (await client.get(WORLDS_URL, headers=other)).json() == {'items': [], 'total': 0}


async def test_null_is_only_for_the_clearable_fields(client: AsyncClient, owner: dict):
    made = await create_world(client, owner, {'genre': 'romance', 'name': '여름 학원'})

    response = await client.patch(f'{WORLDS_URL}/{made["id"]}', json={'name': None}, headers=owner)
    cleared = await client.patch(
        f'{WORLDS_URL}/{made["id"]}', json={'start_slot': None, 'start_place': None, 'image_id': None}, headers=owner
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert cleared.json()['start_slot'] is None


async def test_only_operators_make_a_world_public(open_client: AsyncClient, plain: dict):
    made = await create_world(open_client, plain, {'genre': 'romance', 'name': '여름 학원'})

    response = await open_client.patch(f'{WORLDS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=plain)
    private = await open_client.patch(f'{WORLDS_URL}/{made["id"]}', json={'visibility': 'private'}, headers=plain)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert private.status_code == status.HTTP_200_OK


async def test_an_adult_rating_change_is_checked(open_client: AsyncClient, plain: dict):
    made = await create_world(open_client, plain, {'genre': 'romance', 'name': '여름 학원'})

    response = await open_client.patch(f'{WORLDS_URL}/{made["id"]}', json={'rating': 'adult'}, headers=plain)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'body',
    [
        # 시각이 차례로 커지지 않는다
        {'slots': [{'id': 'a', 'name': '가', 'start_hour': 12}, {'id': 'b', 'name': '나', 'start_hour': 12}]},
        # 같은 id, 같은 이름
        {'slots': [{'id': 'a', 'name': '가', 'start_hour': 1}, {'id': 'a', 'name': '나', 'start_hour': 2}]},
        {'slots': [{'id': 'a', 'name': '가', 'start_hour': 1}, {'id': 'b', 'name': '가', 'start_hour': 2}]},
        # 시간대가 없다, 24시
        {'slots': []},
        {'slots': [{'id': 'a', 'name': '가', 'start_hour': 24}]},
        # 기한
        {'deadline_days': 0},
        {'deadline_days': 366},
        # 보이기의 항목이 두 번
        {'show': {'panel': ['intro', 'intro']}},
        # 같은 장소 id
        {'places': [{'id': 'a', 'name': '가'}, {'id': 'a', 'name': '나'}]},
        {'items': [{'id': 'a', 'name': '가'}, {'id': 'a', 'name': '나'}]},
    ],
)
async def test_bad_fields_are_rejected(client: AsyncClient, owner: dict, body: dict):
    response = await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '여름 학원', **body}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'condition',
    [
        {'kind': 'reach_place'},
        {'kind': 'reach_place', 'target': 'a', 'value': 'b'},
        {'kind': 'hold_item', 'target': 'a', 'value': 'b'},
        {'kind': 'gave_item', 'target': 'a'},
        {'kind': 'affection_at_least', 'value': '친함'},
        {'kind': 'day_at_least', 'target': 'a', 'count': 3},
        {'kind': 'slot_is', 'target': 'a', 'count': 2},
        {'kind': 'accompanied', 'target': 'a', 'count': 0},
    ],
)
async def test_a_condition_fills_only_the_fields_of_its_kind(client: AsyncClient, owner: dict, condition: dict):
    line = {'slot': 'day', 'place': 'a', 'when': {'items': [condition]}}
    cast = [member('ari', str(uuid.uuid4()), schedule=[line])]

    response = await client.post(
        WORLDS_URL, json={'genre': 'romance', 'name': '여름 학원', 'cast': cast}, headers=owner
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_same_character_and_a_still_gift_are_rejected(client: AsyncClient, owner: dict):
    same = str(uuid.uuid4())
    twice = [member('a', same), member('b', same)]
    still = [
        member(
            'a',
            same,
            affection={'stages': [{'name': '낯섦', 'at': 0}], 'gifts': [{'id': 'g', 'item': 'rose', 'change': 0}]},
        )
    ]

    responses = [
        await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '여름', 'cast': cast}, headers=owner)
        for cast in (twice, still)
    ]

    assert [response.status_code for response in responses] == [status.HTTP_422_UNPROCESSABLE_CONTENT] * 2


# --- 가리키기 ---


async def test_the_cast_points_at_my_characters_only(client: AsyncClient, owner: dict, other: dict):
    mine = await character(client, owner)
    theirs = await character(client, other, '버')

    made = await client.post(
        WORLDS_URL, json={'genre': 'romance', 'name': '여', 'cast': [member('ari', mine['id'])]}, headers=owner
    )
    stolen = await client.post(
        WORLDS_URL, json={'genre': 'romance', 'name': '여', 'cast': [member('beo', theirs['id'])]}, headers=owner
    )
    missing = await client.patch(
        f'{WORLDS_URL}/{made.json()["id"]}', json={'cast': [member('x', str(uuid.uuid4()))]}, headers=owner
    )

    assert made.status_code == status.HTTP_201_CREATED
    assert (stolen.status_code, stolen.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'character_not_owned')
    assert missing.json()['code'] == 'character_not_owned'


async def test_the_world_points_at_my_lorebooks_only(client: AsyncClient, owner: dict, other: dict):
    theirs = await client.post(LOREBOOKS_URL, json={'name': '남의 것'}, headers=other)

    response = await client.post(
        WORLDS_URL, json={'genre': 'romance', 'name': '여', 'lorebooks': [theirs.json()['id']]}, headers=owner
    )

    assert (response.status_code, response.json()['code']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'lorebook_not_owned',
    )


async def test_the_same_lorebook_twice_is_rejected(client: AsyncClient, owner: dict):
    made = await client.post(LOREBOOKS_URL, json={'name': '제국'}, headers=owner)
    twice = [made.json()['id']] * 2

    response = await client.post(WORLDS_URL, json={'genre': 'romance', 'name': '여', 'lorebooks': twice}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
