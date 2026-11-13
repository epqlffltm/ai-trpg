# trpg-server/tests/test_monster_patrols.py

"""
조우의 순찰 경로(#254, app/rounds/monster_roams.py 의 순찰)를 검증한다.

판은 사냥과 배회의 수로를 빌린다(tests/test_monster_roams.py). 입구–배수로–깊은 수로는 그냥 가는 길이고,
입구–구덩이는 넘기 판정의 길이다. 들개는 깊은 수로에 있고 엘프는 입구에서 판정만 한다(움직이지 않는다).

보는 것.
  - 순찰은 처음 자리와 경로의 장소들을 차례로 돌고 처음 자리로 돌아온다. 한 라운드에 한 칸이다
  - 경로의 장소가 이웃하지 않아도 가장 짧은 길로 간다. 캐릭터가 선 곳에 들어오면 way 가 patrol 로 적힌다
  - 갈 길이 막혔으면 순찰하지 않고, 배회가 있으면 배회한다
  - 사냥이 순찰보다 먼저다
  - 경로: 같은 장소가 잇달아 오면 422, 로어북에 없는 장소면 게시하지 못한다
"""

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import RouteSnapshot
from app.engine.dice import ScriptedDice
from app.rounds import monster_roams
from app.rounds.monster_scene import SceneMonster
from app.rounds.move_lines import describe_roam
from app.rounds.narrator import RoamNote
from app.tables.models import TableMonster
from tests import test_monster_roams as roams
from tests.sheets import make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

me = roams.me
ANY, ROLL_IN = roams.ANY, roams.ROLL_IN


async def dog(session: AsyncSession) -> TableMonster | None:
    return await session.scalar(select(TableMonster).execution_options(populate_existing=True))


async def test_a_patrol_goes_out_and_comes_back(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await roams.dog_table(client, me, patrol=('drain',))
    dice = roams.load_dice(app, [ANY])

    await roams.stay(client, me, world, narrated)

    # 처음 자리(깊은 수로)에 있으니 다음 곳(배수로)으로 간다
    assert dice.remaining == 0
    walked = await dog(session)
    assert (str(walked.place_id), walked.patrol_leg) == (world['drain']['id'], 1)

    roams.load_dice(app, [ANY])
    await roams.stay(client, me, world, narrated)

    # 배수로에 닿았으니 처음 자리로 돌아간다
    walked = await dog(session)
    assert (str(walked.place_id), walked.patrol_leg) == (world['deep']['id'], 0)
    assert roams.roam_events(await roams.events_of(client, me, world['table'])) == []


async def test_a_patrol_walks_the_shortest_way_and_shows_itself_on_arrival(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await roams.dog_table(client, me, patrol=('gate',))
    roams.load_dice(app, [ANY])
    await roams.stay(client, me, world, narrated)
    assert str((await dog(session)).place_id) == world['drain']['id']

    roams.load_dice(app, [ANY])
    await roams.stay(client, me, world, narrated)

    (arrived,) = roams.roam_events(await roams.events_of(client, me, world['table']))
    assert (arrived['payload']['way'], arrived['payload']['to_place']['name']) == ('patrol', '수로 입구')
    (move,) = await roams.moves_of(session, world['table'], 2)
    assert move['roamed'] == [{'monster': '들개', 'way': 'patrol', 'origin': '배수로'}]


async def test_a_blocked_patrol_stays(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated):
    # 구덩이로 가는 길에는 넘기 판정이 있다
    world = await roams.dog_table(client, me, patrol=('pit',))
    dice = roams.load_dice(app, [ANY])

    await roams.stay(client, me, world, narrated)

    assert dice.remaining == 0
    assert str((await dog(session)).place_id) == world['deep']['id']


async def test_a_blocked_patrol_roams_instead(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await roams.dog_table(client, me, patrol=('pit',), roams={'chance': 50, 'reach': 1})
    dice = roams.load_dice(app, [ANY, ROLL_IN])

    await roams.stay(client, me, world, narrated)

    assert dice.remaining == 0
    assert str((await dog(session)).place_id) == world['drain']['id']


# --- 경로 ---


async def test_the_same_place_twice_in_a_row_is_refused(client: AsyncClient, me: dict):
    world = await roams.make_world(client, me)
    deep, drain = world['deep']['id'], world['drain']['id']
    sheet = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4)}
    body = {'title': '수로', 'bestiary_ids': [world['bestiary']['id']], 'monster_sheets': [sheet]}

    for patrol in ([deep], [drain, drain], [drain, deep]):
        encounter = {'place_id': deep, 'monster_id': world['dog']['id'], 'count': 1, 'patrol': patrol}
        response = await client.post(roams.SCENARIOS_URL, json={**body, 'encounters': [encounter]}, headers=me)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, patrol
        assert 'encounters.0' in response.json()['errors'], patrol


async def test_a_patrol_place_must_be_in_the_lorebook(client: AsyncClient, me: dict):
    world = await roams.make_world(client, me)
    deep = world['deep']['id']
    sheet = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4)}
    encounter = {'place_id': deep, 'monster_id': world['dog']['id'], 'count': 1, 'patrol': [str(uuid.uuid4())]}
    scenario = await roams.post(
        client,
        roams.SCENARIOS_URL,
        me,
        title='수로',
        rulebook_id=world['rulebook']['id'],
        lorebook_ids=[world['lorebook']['id']],
        bestiary_ids=[world['bestiary']['id']],
        openings=['물 떨어지는 소리가 난다.'],
        start_place=world['gate']['id'],
        monster_sheets=[sheet],
        encounters=[encounter],
    )
    assert scenario['encounters'][0]['patrol'] == encounter['patrol']

    response = await client.post(f'{roams.SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'encounter_place_missing' in response.json()['problems']


# --- 작은 함수 ---

A, B, C = (uuid.uuid4() for _ in range(3))


def route(here: uuid.UUID, there: uuid.UUID) -> RouteSnapshot:
    return RouteSnapshot(from_place=here, to_place=there)


def test_the_leg_moves_on_when_reached_and_wraps_around():
    loop = [A, B, C]

    assert monster_roams.current_leg(loop, 0, A) == 1
    assert monster_roams.current_leg(loop, 1, A) == 1
    assert monster_roams.current_leg(loop, 2, C) == 0
    # 경로가 바뀐 판은 없지만, 차례가 길이를 넘어도 돈다
    assert monster_roams.current_leg(loop, 4, A) == 1


def test_hunting_comes_before_patrolling():
    routes = [route(A, B), route(A, C)]
    walker = cast(
        SceneMonster,
        SimpleNamespace(
            state=SimpleNamespace(place_id=A, home_place_id=A, patrol_leg=1),
            definition=SimpleNamespace(hunts=1, roams=None),
        ),
    )

    assert monster_roams.step_of(routes, walker, {C}, ScriptedDice([]), [A, B]) == (C, monster_roams.Way.HUNT)
    assert monster_roams.step_of(routes, walker, set(), ScriptedDice([]), [A, B]) == (B, monster_roams.Way.PATROL)


def test_the_line_tells_a_patrol():
    note = RoamNote(monster='들개', way='patrol', origin='배수로')

    assert describe_roam(note) == '(다가옴: 들개 — 배수로에서 순찰하다 들어왔다, 아직 치지 않음)'
