# game-server/tests/test_scenario_map.py

"""
시나리오의 맵: 시작 장소와 길을 검증한다.

셋을 본다.
  - 시나리오: 적고 읽고 고친다. 모양만 본다(제자리 길 없음, 숨긴 길에만 찾는 판정, 같은 두 장소의 길 하나).
  - 게시: 붙인 로어북의 장소 항목을 가리키는지, 길이 있으면 시작 장소가 있는지, 찾는 판정이 룰북에 맞는지.
  - 판: 형식 19 에 실린다. 옛 판은 맵 없이 읽는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.models import SCENARIO_MAX_ROUTES
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, has_map, place_entries, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_18
from app.main import API_PREFIX
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_npc_sheets import add_entry, create_scenario, post, published, refused
from tests.test_scenario_items import entry, snapshot_document

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만드는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """장소 셋(성문, 광장, 지하실), 물건 하나(치유 물약), 인물 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='성의 장소들')
    return {
        'lorebook': lorebook,
        'gate': await add_entry(client, me, lorebook, '성문', 'place'),
        'square': await add_entry(client, me, lorebook, '광장', 'place'),
        'cellar': await add_entry(client, me, lorebook, '지하실', 'place'),
        'potion': await add_entry(client, me, lorebook, '치유 물약', 'item'),
        'lady': await add_entry(client, me, lorebook, '악역영애', 'person'),
    }


def route(start: dict, end: dict, **fields) -> dict:
    return {'from_place': start['id'], 'to_place': end['id'], **fields}


def secret(start: dict, end: dict, ability: str = 'wis', difficulty: str | None = 'hard') -> dict:
    """숨긴 길. 찾는 판정이 있다."""
    return route(start, end, hidden=True, find={'ability': ability, 'difficulty': difficulty})


async def scenario_with(client: AsyncClient, me: dict, lore: dict, **fields) -> dict:
    """장소 로어북을 붙이고, 인물에게 줄 기본 NPC 시트를 둔 시나리오."""
    return await create_scenario(client, me, lore, default_npc_sheet=SHEET, **fields)


def the_map(lore: dict) -> dict:
    """성문에서 광장으로 가는 길과, 광장에서 지하실로 내려가는 숨긴 한쪽 길. 시작은 성문."""
    return {
        'start_place': lore['gate']['id'],
        'routes': [route(lore['gate'], lore['square']), {**secret(lore['square'], lore['cellar']), 'two_way': False}],
    }


# --- 시나리오: 적고 읽고 고친다 ---


async def test_the_map_is_saved_and_read_back(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, **the_map(lore))

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    # 양쪽으로 다니고, 숨기지 않은 것이 기본이다
    assert read['start_place'] == lore['gate']['id']
    assert read['routes'] == [
        {
            'from_place': lore['gate']['id'],
            'to_place': lore['square']['id'],
            'two_way': True,
            'hidden': False,
            'find': None,
        },
        {
            'from_place': lore['square']['id'],
            'to_place': lore['cellar']['id'],
            'two_way': False,
            'hidden': True,
            'find': {'ability': 'wis', 'difficulty': 'hard'},
        },
    ]


async def test_a_scenario_starts_without_a_map(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    assert (scenario['start_place'], scenario['routes']) == (None, [])


async def test_routes_are_replaced_as_a_whole_and_the_start_can_be_cleared(
    client: AsyncClient, me: dict[str, str], lore: dict
):
    scenario = await scenario_with(client, me, lore, **the_map(lore))
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    replaced = await client.patch(url, json={'routes': [route(lore['square'], lore['cellar'])]}, headers=me)
    cleared = await client.patch(url, json={'start_place': None}, headers=me)

    assert replaced.status_code == status.HTTP_200_OK, replaced.text
    assert [(item['from_place'], item['to_place']) for item in replaced.json()['routes']] == [
        (lore['square']['id'], lore['cellar']['id'])
    ]
    # 보내지 않은 칸은 그대로고, null 을 보내면 비운다
    assert replaced.json()['start_place'] == lore['gate']['id']
    assert (cleared.json()['start_place'], len(cleared.json()['routes'])) == (None, 1)


A = '00000000-0000-4000-8000-00000000000a'
B = '00000000-0000-4000-8000-00000000000b'


@pytest.mark.parametrize(
    'routes',
    [
        [{'from_place': A, 'to_place': A}],
        [{'from_place': A, 'to_place': B, 'hidden': True}],
        [{'from_place': A, 'to_place': B, 'find': {'ability': 'wis'}}],
        [{'from_place': A, 'to_place': B}, {'from_place': A, 'to_place': B, 'two_way': False}],
        [{'from_place': A, 'to_place': B}, {'from_place': B, 'to_place': A}],
        [{'from_place': A, 'to_place': B, 'extra': 1}],
        [{'from_place': A, 'to_place': B, 'hidden': True, 'find': {'ability': 'Wisdom!'}}],
        [{'from_place': A, 'to_place': B, 'hidden': True, 'find': {'ability': 'wis', 'roll': 20}}],
        [{'from_place': str(uuid.uuid4()), 'to_place': str(uuid.uuid4())} for _ in range(SCENARIO_MAX_ROUTES + 1)],
    ],
    ids=[
        'to-itself',
        'hidden-without-find',
        'find-without-hidden',
        'same-pair-twice',
        'same-pair-reversed',
        'extra-field',
        'bad-ability-key',
        'extra-find-field',
        'too-many-routes',
    ],
)
async def test_rejects_badly_shaped_routes(client: AsyncClient, me: dict[str, str], routes: list):
    response = await client.post(SCENARIOS_URL, json={'title': '성', 'routes': routes}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_accepts_the_most_routes_allowed(client: AsyncClient, me: dict[str, str]):
    routes = [{'from_place': str(uuid.uuid4()), 'to_place': str(uuid.uuid4())} for _ in range(SCENARIO_MAX_ROUTES)]

    scenario = await create_scenario(client, me, None, routes=routes)

    assert len(scenario['routes']) == SCENARIO_MAX_ROUTES


# --- 게시 ---


async def test_the_map_is_frozen_into_the_version(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, **the_map(lore))

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT == 19
    assert snapshot['start_place'] == lore['gate']['id']
    assert snapshot['routes'][1] == {
        'from_place': lore['square']['id'],
        'to_place': lore['cellar']['id'],
        'two_way': False,
        'hidden': True,
        'find': {'ability': 'wis', 'difficulty': 'hard'},
    }


async def test_a_start_alone_is_a_map(client: AsyncClient, me: dict[str, str], lore: dict):
    # 길 없이 장소 하나에 서 있는 것도 맵이다. 방장이 옮기거나 나중에 길을 더한다
    scenario = await scenario_with(client, me, lore, start_place=lore['square']['id'])

    snapshot = await published(client, me, scenario)

    assert (snapshot['start_place'], snapshot['routes']) == (lore['square']['id'], [])


@pytest.mark.parametrize('where', ['start', 'route'])
async def test_the_map_must_be_in_an_attached_lorebook(client: AsyncClient, me: dict[str, str], lore: dict, where: str):
    gone = {'id': NO_SUCH_ID}
    fields = {
        'start': {'start_place': NO_SUCH_ID},
        'route': {'start_place': lore['gate']['id'], 'routes': [route(lore['gate'], gone)]},
    }[where]
    scenario = await scenario_with(client, me, lore, **fields)

    assert await refused(client, me, scenario) == ['map_place_missing']


@pytest.mark.parametrize(('where', 'kind'), [('start', 'potion'), ('route', 'lady')])
async def test_the_map_must_be_places(client: AsyncClient, me: dict[str, str], lore: dict, where: str, kind: str):
    fields = {
        'start': {'start_place': lore[kind]['id']},
        'route': {'start_place': lore['gate']['id'], 'routes': [route(lore['gate'], lore[kind])]},
    }[where]
    scenario = await scenario_with(client, me, lore, **fields)

    assert await refused(client, me, scenario) == ['map_not_place']


async def test_routes_need_a_start(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, routes=[route(lore['gate'], lore['square'])])

    assert await refused(client, me, scenario) == ['map_start_missing']


@pytest.mark.parametrize(('ability', 'difficulty'), [('luck', 'hard'), ('wis', 'impossible')])
async def test_finding_must_follow_the_rulebook(
    client: AsyncClient, me: dict[str, str], lore: dict, ability: str, difficulty: str
):
    fields = {'start_place': lore['gate']['id'], 'routes': [secret(lore['gate'], lore['cellar'], ability, difficulty)]}
    scenario = await scenario_with(client, me, lore, **fields)

    assert await refused(client, me, scenario) == ['route_find_invalid']


async def test_finding_without_a_difficulty_uses_the_default(client: AsyncClient, me: dict[str, str], lore: dict):
    fields = {'start_place': lore['gate']['id'], 'routes': [secret(lore['gate'], lore['cellar'], difficulty=None)]}
    scenario = await scenario_with(client, me, lore, **fields)

    snapshot = await published(client, me, scenario)

    assert snapshot['routes'][0]['find'] == {'ability': 'wis', 'difficulty': None}


async def test_a_map_in_a_detached_lorebook_is_missing(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await scenario_with(client, me, lore, **the_map(lore))

    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': []}, headers=me)

    # 로어북을 떼면 그 장소도 사라진다. 굳히기 전에 막는다
    assert await refused(client, me, scenario) == ['map_place_missing']


# --- 판 ---


GATE = uuid.UUID('dddddddd-0000-4000-8000-000000000001')
SQUARE = uuid.UUID('dddddddd-0000-4000-8000-000000000002')
POTION = uuid.UUID('dddddddd-0000-4000-8000-000000000003')
INN_KEEPER = uuid.UUID('dddddddd-0000-4000-8000-000000000004')


def map_document(**fields) -> dict:
    """판 하나의 문서. 장소 둘, 물건 하나, 인물 하나가 든 로어북이 붙어 있다. 형식 19."""
    lorebook = {
        'id': str(uuid.uuid4()),
        'title': '로어북',
        'entries': [entry(GATE, 'place'), entry(POTION, 'item'), entry(INN_KEEPER, 'person'), entry(SQUARE, 'place')],
    }
    document = {'format': 19, 'lorebooks': [lorebook], 'quests': [], 'start_place': None, 'routes': [], **fields}
    return snapshot_document(**document)


def test_places_are_the_place_entries_and_a_start_makes_a_map():
    without = Snapshot.model_validate(map_document())
    with_start = Snapshot.model_validate(map_document(start_place=str(GATE)))

    assert [entry.id for entry in place_entries(with_start)] == [GATE, SQUARE]
    assert (has_map(without), has_map(with_start)) == (False, True)


@pytest.mark.parametrize(
    'fields',
    [
        {'start_place': str(POTION)},
        {'start_place': str(uuid.uuid4())},
        {'start_place': str(GATE), 'routes': [{'from_place': str(GATE), 'to_place': str(POTION)}]},
        {'routes': [{'from_place': str(GATE), 'to_place': str(SQUARE)}]},
    ],
    ids=['start-on-a-thing', 'unknown-start', 'route-to-a-thing', 'routes-without-start'],
)
def test_a_version_cannot_point_the_map_at_anything_but_places(fields: dict):
    # 게시가 막는 것을 판의 계약으로도 굳혀 둔다. 테이블은 위치마다 장소 항목이 있다고 믿고 쓴다
    with pytest.raises(ValidationError):
        Snapshot.model_validate(map_document(**fields))


def test_an_old_version_is_read_without_a_map():
    document = map_document(format=18)
    del document['start_place'], document['routes']

    upgraded = upgrade_from_18(document)
    snapshot = read_snapshot(document)

    assert (upgraded['format'], upgraded['start_place'], upgraded['routes']) == (19, None, [])
    # 받은 문서는 고치지 않는다
    assert 'routes' not in document
    assert (snapshot.start_place, snapshot.routes, has_map(snapshot)) == (None, [], False)
