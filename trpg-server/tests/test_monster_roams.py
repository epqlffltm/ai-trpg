# trpg-server/tests/test_monster_roams.py

"""
싸우지 않는 몬스터의 사냥과 배회(#254, app/rounds/monster_roams.py)를 검증한다.

판은 여기서 만든다. 장소는 수로 입구(시작), 배수로, 깊은 수로, 구덩이다.
입구–배수로–깊은 수로는 그냥 가는 길이고, 입구–구덩이는 넘기 판정(근력)이 있는 길이다.
들개 한 마리를 깊은 수로(입구에서 두 칸)나 구덩이에 둔다(야수, 최대 HP 4, 물기). 시트에 사냥이나 배회를 적는다.
엘프는 입구에 서서 판정하는 행동만 한다(움직이지 않는다). 들개는 장면에 없어 차례를 받지 않는다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 엘프의 판정이 먼저, 배회의 확률이 그다음이다.

보는 것.
  - 사냥: 두 칸 안의 엘프에게 한 칸씩 다가간다. 아무도 없는 배수로로 간 것은 적지 않고, 입구에 들어오면
    monster_roamed 가 적히고 그곳의 서술에 (다가옴: …)이 붙는다. 그다음 라운드에 장면에 들어 친다
  - 사냥의 거리 밖이면 움직이지 않는다. 넘기 판정이 있는 길은 지나지 못한다
  - 배회: 확률에 들면 이웃으로 가고, 처음 자리에서 한도 밖으로는 가지 않는다. 확률에 못 들면 그대로다
  - 장면에 있는 마리(싸우는 마리)는 사냥하거나 배회하지 않는다
  - 시트: 사냥의 거리와 배회의 확률·한도의 범위, 판에 굳힘
  - 작은 함수: 가장 가까운 곳과 같은 거리의 순서, 한쪽으로만 가는 길
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import RouteSnapshot
from app.engine.dice import ScriptedDice
from app.rounds import monster_roams
from app.rounds.move_lines import describe_roam
from app.rounds.narrator import RoamNote
from app.tables import places
from app.tables.models import TableMonster
from app.transcripts.story import roamed
from tests.sheets import SHEET, make_sheet
from tests.test_monster_turns import (
    BESTIARIES_URL,
    LOREBOOKS_URL,
    ME,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    declare,
    events_of,
    load_dice,
    moves_of,
    post,
    table_url,
    turns_of,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
CHECK = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}
# 엘프의 판정(아무거나), 배회의 확률(50 이하면 든다)
ANY, ROLL_IN, ROLL_OUT = 10, 50, 51
# 차례의 주사위. 큰 눈이 먼저다. 들개의 물기(빗나감)
EARLY, LATE, MISS = 20, 1, 1


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def make_world(client: AsyncClient, me: dict) -> dict:
    """수로 입구, 배수로, 깊은 수로, 구덩이가 든 로어북. 들개가 든 도감. 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, url, me, name='수로 입구', kind='place'),
        'drain': await post(client, url, me, name='배수로', kind='place'),
        'deep': await post(client, url, me, name='깊은 수로', kind='place'),
        'pit': await post(client, url, me, name='구덩이', kind='place'),
        'dog': await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='들개', kind='beast'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


async def dog_table(client: AsyncClient, me: dict, at: str = 'deep', **moves) -> dict:
    """들개 한 마리를 at 에 둔 테이블. moves 는 시트의 hunts, roams 다. 나 혼자 입구에 앉는다."""
    world = await make_world(client, me)
    gate, drain, deep, pit = (world[name]['id'] for name in ('gate', 'drain', 'deep', 'pit'))
    dog = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4), 'attacks': [BITE], **moves}
    routes = [
        {'from_place': gate, 'to_place': drain},
        {'from_place': drain, 'to_place': deep},
        {'from_place': gate, 'to_place': pit, 'cross': {'ability': 'str'}},
    ]
    body = {
        'title': '지하 수로',
        'rulebook_id': world['rulebook']['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'start_place': gate,
        'routes': routes,
        'monster_sheets': [dog],
        'encounters': [{'place_id': world[at]['id'], 'monster_id': world['dog']['id'], 'count': 1}],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': table}


async def stay(client: AsyncClient, me: dict, world: dict, narrated) -> None:
    """엘프가 입구에서 판정하는 행동만 하고 라운드를 닫는다."""
    await declare(client, me, world['table'], '주위를 살핀다.', CHECK)
    await narrated()


async def dog_place(session: AsyncSession) -> str:
    row = await session.scalar(select(TableMonster).execution_options(populate_existing=True))
    return str(row.place_id)


def roam_events(seen: list[dict]) -> list[dict]:
    return [event for event in seen if event['type'] == 'monster_roamed']


async def test_a_hunter_closes_in_one_step_a_round_and_shows_itself_on_arrival(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, hunts=2)
    dice = load_dice(app, [ANY])

    await stay(client, me, world, narrated)

    # 아무도 없는 배수로로 왔다. 적지 않는다
    assert dice.remaining == 0
    assert await dog_place(session) == world['drain']['id']
    assert roam_events(await events_of(client, me, world['table'])) == []

    load_dice(app, [ANY])
    await stay(client, me, world, narrated)

    assert await dog_place(session) == world['gate']['id']
    (arrived,) = roam_events(await events_of(client, me, world['table']))
    assert arrived['payload'] == {
        'round': 2,
        'monster_id': arrived['payload']['monster_id'],
        'name': '들개',
        'way': 'hunt',
        'from_place': {'entry_id': world['drain']['id'], 'name': '배수로'},
        'to_place': {'entry_id': world['gate']['id'], 'name': '수로 입구'},
    }
    (move,) = await moves_of(session, world['table'], 2)
    assert move['roamed'] == [{'monster': '들개', 'way': 'hunt', 'origin': '배수로'}]
    # 들어온 라운드에는 치지 않았다
    assert await turns_of(session, world['table'], 2) == []


async def test_the_round_after_arriving_the_hunter_strikes(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, at='drain', hunts=1)
    load_dice(app, [ANY])
    await stay(client, me, world, narrated)
    assert await dog_place(session) == world['gate']['id']
    # 차례의 주사위(엘프, 들개), 엘프의 판정, 들개의 물기(빗나감)
    dice = load_dice(app, [EARLY, LATE, ANY, MISS])

    await stay(client, me, world, narrated)

    assert dice.remaining == 0
    bite = next(turn for turn in await turns_of(session, world['table'], 2) if turn['kind'] == 'monster')
    assert (bite['outcome']['attack']['name'], bite['outcome']['success']) == ('물기', False)


async def test_a_hunter_out_of_reach_or_behind_a_climb_stays(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    far = await dog_table(client, me, hunts=1)
    load_dice(app, [ANY])
    await stay(client, me, far, narrated)
    assert await dog_place(session) == far['deep']['id']


async def test_a_hunter_cannot_climb(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated):
    world = await dog_table(client, me, at='pit', hunts=3)
    dice = load_dice(app, [ANY])

    await stay(client, me, world, narrated)

    assert dice.remaining == 0
    assert await dog_place(session) == world['pit']['id']


async def test_a_roamer_wanders_but_keeps_near_its_home(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, roams={'chance': 50, 'reach': 1})
    # 확률에 든다. 깊은 수로의 이웃은 배수로 하나라 고르지 않는다
    dice = load_dice(app, [ANY, ROLL_IN])
    await stay(client, me, world, narrated)
    assert dice.remaining == 0
    assert await dog_place(session) == world['drain']['id']

    # 또 든다. 입구는 처음 자리에서 두 칸이라 한도 밖이다. 남은 이웃은 깊은 수로뿐이다
    dice = load_dice(app, [ANY, ROLL_IN])
    await stay(client, me, world, narrated)
    assert dice.remaining == 0
    assert await dog_place(session) == world['deep']['id']
    assert roam_events(await events_of(client, me, world['table'])) == []


async def test_a_roamer_that_misses_its_chance_stays(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, roams={'chance': 50, 'reach': 3})
    dice = load_dice(app, [ANY, ROLL_OUT])

    await stay(client, me, world, narrated)

    assert dice.remaining == 0
    assert await dog_place(session) == world['deep']['id']


async def test_a_monster_in_the_scene_does_not_roam(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, at='gate', hunts=2, roams={'chance': 100, 'reach': 3})
    # 차례의 주사위(엘프, 들개), 엘프의 판정, 들개의 물기(빗나감). 배회의 확률은 굴리지 않는다
    dice = load_dice(app, [EARLY, LATE, ANY, MISS])

    await stay(client, me, world, narrated)

    assert dice.remaining == 0
    assert await dog_place(session) == world['gate']['id']


async def test_a_monster_left_behind_this_round_does_not_hunt_yet(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, at='gate', hunts=2)
    # 차례의 주사위(엘프가 먼저, 들개). 엘프는 굴리지 않고 배수로로 간다. 들개는 칠 사람이 없다(쫓지 않는다)
    dice = load_dice(app, [EARLY, LATE])

    await declare(client, me, world['table'], '배수로로 간다.', {'kind': 'move', 'place': world['drain']['id']})
    await narrated()

    # 이번 라운드에 장면에 있던 마리는 차례를 받았다. 사냥은 다음 라운드부터다
    assert dice.remaining == 0
    assert await dog_place(session) == world['gate']['id']


# --- 시트 ---


@pytest.mark.parametrize(
    'moves',
    [
        {'hunts': 0},
        {'hunts': 6},
        {'roams': {'chance': 0, 'reach': 1}},
        {'roams': {'chance': 50, 'reach': 6}},
        {'roams': {'chance': 50}},
    ],
    ids=['hunts-0', 'hunts-6', 'chance-0', 'reach-6', 'reach-missing'],
)
async def test_the_sheet_bounds_the_moves(client: AsyncClient, me: dict, moves: dict):
    world = await make_world(client, me)
    dog = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4), **moves}

    response = await client.post(
        SCENARIOS_URL,
        json={'title': '수로', 'bestiary_ids': [world['bestiary']['id']], 'monster_sheets': [dog]},
        headers=me,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_moves_are_kept_on_the_sheet(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    roams = {'chance': 30, 'reach': 2}
    dog = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4), 'hunts': 3, 'roams': roams}

    made = await post(
        client, SCENARIOS_URL, me, title='수로', bestiary_ids=[world['bestiary']['id']], monster_sheets=[dog]
    )

    (sheet,) = made['monster_sheets']
    assert (sheet['hunts'], sheet['roams']) == (3, roams)


# --- 작은 함수 ---

A, B, C, D = (uuid.uuid4() for _ in range(4))


def route(here: uuid.UUID, there: uuid.UUID, two_way: bool = True) -> RouteSnapshot:
    return RouteSnapshot(from_place=here, to_place=there, two_way=two_way)


def test_the_hunter_takes_the_first_shortest_way_in_route_order():
    # A 에서 C 로는 B 를 거치거나 D 를 거친다. 둘 다 두 칸이라 길 순서가 앞인 B 로 간다
    routes = [route(A, B), route(A, D), route(B, C), route(D, C)]

    assert monster_roams.hunt_step(routes, A, 2, {C}) == B
    assert monster_roams.hunt_step(routes, A, 1, {C}) is None
    # 가장 가까운 곳이 먼저다(D 는 한 칸)
    assert monster_roams.hunt_step(routes, A, 2, {C, D}) == D


def test_a_one_way_route_is_walked_one_way():
    routes = [route(A, B, two_way=False)]

    assert monster_roams.next_places(routes, A) == [B]
    assert monster_roams.next_places(routes, B) == []
    assert monster_roams.hunt_step(routes, B, 3, {A}) is None


def test_a_roamer_picks_a_neighbour_near_home_with_the_dice():
    routes = [route(A, B), route(A, C), route(C, D)]
    dog = SimpleNamespace(
        state=SimpleNamespace(place_id=A, home_place_id=A),
        definition=SimpleNamespace(roams=SimpleNamespace(chance=50, reach=1)),
    )

    # 확률(50 이하), 이웃 둘(B, C) 중 두 번째
    assert monster_roams.roam_step(routes, dog, ScriptedDice([50, 2])) == C
    assert monster_roams.roam_step(routes, dog, ScriptedDice([51])) is None


# --- 서술과 기록 ---


def test_the_lines_tell_the_arrival():
    hunter = RoamNote(monster='들개', way='hunt', origin='배수로')
    roamer = RoamNote(monster='들개', way='roam')

    assert describe_roam(hunter) == '(다가옴: 들개 — 배수로에서 냄새를 맡고 다가왔다, 아직 치지 않음)'
    assert describe_roam(roamer) == '(다가옴: 들개 — 어슬렁거리다 들어왔다, 아직 치지 않음)'
    payload = {'name': '들개', 'way': 'roam', 'from_place': None, 'to_place': {'entry_id': str(A), 'name': '수로 입구'}}
    assert roamed(payload, None)[0].text == '들개: 어슬렁거리다 들어옴 · 수로 입구'


def test_hunting_comes_before_roaming():
    routes = [route(A, B), route(A, C)]
    dog = SimpleNamespace(
        state=SimpleNamespace(place_id=A, home_place_id=A),
        definition=SimpleNamespace(hunts=1, roams=SimpleNamespace(chance=100, reach=3)),
    )

    # 사냥할 것이 있으면 배회의 확률을 굴리지 않는다
    assert monster_roams.step_of(routes, dog, {C}, ScriptedDice([])) == (C, monster_roams.Way.HUNT)
    assert monster_roams.step_of(routes, dog, set(), ScriptedDice([100, 1])) == (B, monster_roams.Way.ROAM)


def test_a_place_the_table_does_not_know_is_not_named():
    entry = SimpleNamespace(id=A, name='깊은 수로')
    snapshot = SimpleNamespace(lorebooks=[])
    known = places.KnownMap(places=[entry], routes=[])

    assert monster_roams.place_document(snapshot, known, B) is None
    assert monster_roams.place_document(snapshot, None, A) is None
