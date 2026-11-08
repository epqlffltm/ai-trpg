# trpg-server/tests/test_submaps.py

"""
장소가 품은 하위 맵(#284)을 검증한다. 마을 안의 건물, 건물의 층, 던전의 층이다.

맵과 픽스처는 tests/test_table_map.py 의 것이다.
성문에서 시작하고 광장, 숨긴 한쪽 길의 지하실, 안개 길의 숲과 오두막, 명소의 탑이 있다.
맵 밖의 장소(지하 감옥)와 사건 항목은 tests/test_happenings.py 의 것이다.

보는 것.
  - 시나리오: 하위 맵을 저장하고 판에 굳힌다. 품은 장소가 자기 안에 들거나, 한 장소가 두 하위 맵에 들거나,
    한 장소가 하위 맵을 둘 품거나, 서로를 품거나, 너무 깊으면 저장할 때 422 다.
    붙인 로어북에 없는 장소, 장소가 아닌 항목, 맵에 없는 장소를 담으면 게시하지 못한다(409).
  - 테이블: 아는 장소마다 품은 장소(inside)가 있다. 품은 장소를 모르면 null 이다. 하위 맵 안으로도 보통의 길로 간다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들(품은 장소 찾기, 서술의 장소 줄)의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.schemas import submap_depth
from app.assets.scenarios.snapshot import SubmapSnapshot, container_of, containers_of, read_snapshot
from app.rounds.moves import known_containers
from app.rounds.narrator import PlaceNote
from app.rounds.prompt import map_line
from tests import test_happenings as happenings
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_map_actions import going, play
from tests.test_table_items import SCENARIOS_URL, post, read_table, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
more = happenings.more


def submap(container: dict, *places: dict) -> dict:
    return {'place_id': container['id'], 'places': [place['id'] for place in places]}


def nested(lore: dict) -> list[dict]:
    """숲이 오두막을, 광장이 지하실을, 지하실이 탑을 품는다. 탑은 명소라 처음부터 알지만 지하실은 모른다."""
    return [
        submap(lore['forest'], lore['hut']),
        submap(lore['square'], lore['cellar']),
        submap(lore['cellar'], lore['tower']),
    ]


async def draft(client: AsyncClient, me: dict, lore: dict, submaps: list[dict]) -> dict:
    """그 하위 맵들을 적은 시나리오. 맵은 the_map 이다. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        **map_tables.the_map(lore),
        'submaps': submaps,
    }
    return await post(client, SCENARIOS_URL, me, **body)


# --- 시나리오 ---


async def test_submaps_are_saved_and_published(client: AsyncClient, me: dict, lore: dict):
    scenario = await draft(client, me, lore, nested(lore))

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['submaps'] == nested(lore)
    published = read_snapshot(response.json()['snapshot']).submaps
    assert [(one.place_id, one.places) for one in published] == [
        (uuid.UUID(lore['forest']['id']), [uuid.UUID(lore['hut']['id'])]),
        (uuid.UUID(lore['square']['id']), [uuid.UUID(lore['cellar']['id'])]),
        (uuid.UUID(lore['cellar']['id']), [uuid.UUID(lore['tower']['id'])]),
    ]


def ids(count: int) -> list[dict]:
    return [{'id': str(uuid.uuid4())} for _ in range(count)]


def broken(case: str) -> list[dict]:
    """저장할 때 거부하는 하위 맵들. 장소가 로어북에 있는지는 저장할 때 보지 않으므로 아무 ID 나 쓴다."""
    a, b, c, d, e = ids(5)
    return {
        'holds_itself': [submap(a, a, b)],
        'in_two': [submap(a, c), submap(b, c)],
        'held_twice': [submap(a, b), submap(a, c)],
        'cycle': [submap(a, b), submap(b, a)],
        'too_deep': [submap(a, b), submap(b, c), submap(c, d), submap(d, e)],
        'repeated': [submap(a, b, b)],
        'empty': [{'place_id': a['id'], 'places': []}],
    }[case]


@pytest.mark.parametrize('case', ['holds_itself', 'in_two', 'held_twice', 'cycle', 'too_deep', 'repeated', 'empty'])
async def test_a_wrong_shape_is_refused_when_saved(client: AsyncClient, me: dict, case: str):
    body = {'title': '성의 모험', 'submaps': broken(case)}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_three_levels_deep_is_allowed(client: AsyncClient, me: dict):
    a, b, c, d = ids(4)
    body = {'title': '성의 모험', 'submaps': [submap(a, b), submap(b, c), submap(c, d)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text


@pytest.mark.parametrize(
    ('case', 'problem'),
    [('missing', 'submap_place_missing'), ('item', 'submap_not_place'), ('off_map', 'submap_off_map')],
)
async def test_a_submap_must_hold_places_on_the_map(client: AsyncClient, me: dict, more: dict, case: str, problem: str):
    inner = {'missing': {'id': str(uuid.uuid4())}, 'item': more['potion'], 'off_map': more['dungeon']}[case]
    scenario = await draft(client, me, more, [submap(more['forest'], more['hut'], inner)])

    response = await happenings.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert problem in response.json()['problems']


# --- 테이블 ---


def insides(table: dict) -> dict[str, str | None]:
    return {place['name']: place['inside'] for place in table['map']['places']}


async def test_a_known_place_tells_which_place_holds_it(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await map_tables.open_duo(client, me, friend, lore, **map_tables.the_map(lore), submaps=nested(lore))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text

    # 처음에는 성문, 광장, 숲(안개 길의 끝), 탑(명소)을 안다. 오두막은 모른다.
    # 탑을 품은 지하실은 모르는 곳이라 null 이다. 바깥 맵의 장소도 null 이다
    seen = await read_table(client, friend, table)
    assert insides(seen) == {'성문': None, '광장': None, '숲': None, '탑': None}

    # 숲에 들어서면 오두막으로 가는 안개 길이 보인다. 오두막은 숲이 품은 곳이다
    await play(client, me, friend, table, narrated, mine=going(lore['forest']))

    seen = await read_table(client, friend, table)
    assert insides(seen)['오두막'] == lore['forest']['id']

    # 하위 맵 안으로도 보통의 길로 간다
    await play(client, me, friend, table, narrated, mine=going(lore['hut']))

    mine = next(member for member in (await read_table(client, me, table))['members'] if member['is_host'])
    assert mine['sheet']['place_id'] == lore['hut']['id']


# --- 작은 함수들 ---

TOWN = uuid.UUID('00000000-0000-4000-8000-0000000000c1')
INN = uuid.UUID('00000000-0000-4000-8000-0000000000c2')
FLOOR = uuid.UUID('00000000-0000-4000-8000-0000000000c3')
FIELD = uuid.UUID('00000000-0000-4000-8000-0000000000c4')
SUBMAPS = SimpleNamespace(
    submaps=[SubmapSnapshot(place_id=TOWN, places=[INN]), SubmapSnapshot(place_id=INN, places=[FLOOR])]
)


def test_the_holders_are_listed_from_the_outside_in():
    assert containers_of(SUBMAPS, FLOOR) == [TOWN, INN]
    assert containers_of(SUBMAPS, INN) == [TOWN]
    assert containers_of(SUBMAPS, FIELD) == []
    assert (container_of(SUBMAPS, FLOOR), container_of(SUBMAPS, TOWN)) == (INN, None)


def test_a_loop_stops_after_one_turn():
    looped = SimpleNamespace(
        submaps=[SubmapSnapshot(place_id=TOWN, places=[INN]), SubmapSnapshot(place_id=INN, places=[TOWN])]
    )

    assert containers_of(looped, INN) == [TOWN]
    assert submap_depth(TOWN, {INN: TOWN, TOWN: INN}) is None
    assert submap_depth(FLOOR, {FLOOR: INN, INN: TOWN}) == 3


def test_the_narration_names_only_the_known_holders():
    names = {TOWN: '마을', INN: '여관', FLOOR: '2층'}
    everything = SimpleNamespace(snapshot=SUBMAPS, names=names, known=SimpleNamespace(has=lambda place: True))
    no_town = SimpleNamespace(snapshot=SUBMAPS, names=names, known=SimpleNamespace(has=lambda place: place != TOWN))
    no_map = SimpleNamespace(snapshot=SUBMAPS, names=names, known=None)

    assert known_containers(everything, FLOOR) == ['마을', '여관']
    assert known_containers(no_town, FLOOR) == ['여관']
    assert known_containers(no_map, FLOOR) == []


def test_the_map_line_puts_the_holders_before_the_name():
    inside = PlaceNote(name='2층', exits=['여관 1층'], path=['마을', '여관'])
    outside = PlaceNote(name='광장', exits=['성문'])

    assert map_line('2층', ['기사'], inside) == '- 마을 > 여관 > 2층(기사): 나가는 길: 여관 1층'
    assert map_line('광장', ['기사'], outside) == '- 광장(기사): 나가는 길: 성문'
