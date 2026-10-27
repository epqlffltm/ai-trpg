# trpg-server/tests/test_route_repair.py

"""
부서진 문을 고치는 것(#281, 행동 '고치기')을 검증한다.

맵과 물건은 tests/test_route_doors.py 의 것이다. 시작은 성문이다. 여기에 물건 하나(망치)를 더하고 고치는 판정을 단다.
  - 성문-숲: 숲 쪽의 빗장(걸림). 근력으로 부수고, 근력으로 고친다(도구가 있어야 한다, 망치가 고치기를 거든다, #802.
    난이도는 비워 보통 15).
  - 성문-광장: 탑 열쇠의 자물쇠(잠김). 민첩·어려움(20)으로 고친다(도구 없이).
  - 성문-오두막: 고치는 판정이 없다.
시트의 능력치는 모두 10(보정 0)이다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 고치는 판정을 저장하고 판에 굳힌다. 문이 없는 길에 적으면 422, 규칙에 없는 능력이면 409 의 문제다.
    도구가 있어야 하면 고치기를 거드는 물건이 판에 있어야 한다. 옛 판은 고치는 판정이 없는 것으로 읽는다.
  - 맵: 고치는 판정과 도구가 있어야 하는지가 보인다.
  - 고치기: 부서진 문만, 도구가 있어야 하면 붙인 도구를 지녀야 굴리고, 성공하면 고쳐져 열린 채다.
    고친 문은 다시 잠근다.
    판에 고치는 판정이 없으면 받지 않는다(409 not_repairable).
  - 이벤트와 서술: 해낸 것만 door_changed(act repair), 굴린 것은 check_rolled. 한 일의 줄과 기록의 글.
"""

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_54
from app.rounds import prompt
from app.rounds.move_lines import describe_door
from app.rounds.narrator import DoorNote
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests import test_route_doors as route_doors
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import play
from tests.test_table_items import ME, SCENARIOS_URL, events_of, give, post, read_table, table_url
from tests.test_table_items import take as take_away
from tests.test_table_map import open_duo, put_at, route
from tests.test_transcript_markdown import event
from tests.transcript_samples import SAMPLES

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
gear = route_doors.gear
door = route_doors.door
declare = route_doors.declare
door_outcome = route_doors.door_outcome
route_out = route_doors.route_out


@pytest.fixture
async def tools(client: AsyncClient, me: dict, gear: dict) -> dict:
    """같은 로어북에 물건 하나(망치)를 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{gear["lorebook"]["id"]}/entries'
    hammer = await post(client, url, me, name='망치', keywords=[], content='망치의 설명', kind='item')
    return {**gear, 'hammer': hammer}


def the_routes(tools: dict) -> list[dict]:
    """route_doors 의 길에 고치는 판정을 단다. 성문-오두막은 고치지 못한다."""
    square, forest, tower, hut = route_doors.the_routes(tools)
    return [
        {**square, 'repair': {'ability': 'dex', 'difficulty': 'hard'}},
        {**forest, 'repair': {'ability': 'str', 'needs_tool': True}},
        tower,
        hut,
    ]


def the_items(tools: dict) -> list[dict]:
    """route_doors 의 락픽에 더해, 망치는 고치기를 거든다(#802). 보정이 없고 없어지지 않는다."""
    return [*route_doors.the_items(tools), {'entry_id': tools['hammer']['id'], 'aids': [{'act': 'repair'}]}]


def the_map(tools: dict) -> dict:
    return {'start_place': tools['gate']['id'], 'routes': the_routes(tools), 'items': the_items(tools)}


async def start(client: AsyncClient, me: dict, friend: dict, tools: dict) -> dict:
    """고치는 판정을 단 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, tools, **the_map(tools))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def break_door(session: AsyncSession, table: dict, one: dict, other: dict) -> None:
    """그 길의 문을 부순다(부수기에 성공한 것과 같은 값). 행동을 거치지 않고 마련한다."""
    await session.execute(
        text(
            'UPDATE table_route_locks SET locked = false, barred = false, broken = true '
            'WHERE table_id = :table_id AND from_place = :one AND to_place = :other'
        ),
        {'table_id': table['id'], 'one': one['id'], 'other': other['id']},
    )
    await session.commit()


# --- 시나리오 ---


async def test_repair_checks_are_saved_and_published(client: AsyncClient, me: dict, tools: dict):
    scenario = await route_doors.draft(client, me, tools, routes=the_routes(tools), items=the_items(tools))

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    square, forest, tower, _ = scenario['routes']
    assert square['repair'] == {'ability': 'dex', 'difficulty': 'hard', 'needs_tool': False}
    assert forest['repair'] == {'ability': 'str', 'difficulty': None, 'needs_tool': True}
    assert tower['repair'] is None
    routes = read_snapshot(response.json()['snapshot']).routes
    assert (routes[1].repair.ability, routes[1].repair.needs_tool) == ('str', True)
    assert routes[2].repair is None


@pytest.mark.parametrize('case', ['without-door', 'unknown-field'])
async def test_a_misshaped_repair_is_refused(client: AsyncClient, me: dict, tools: dict, case: str):
    fields = {
        'without-door': {'repair': {'ability': 'str'}},
        'unknown-field': {'lock': {'key': tools['tower_key']['id']}, 'repair': {'ability': 'str', 'noise': 1}},
    }
    body = {'title': '성의 모험', 'routes': [route(tools['gate'], tools['square'], **fields[case])]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('ability', 'route_open_invalid'),
        ('difficulty', 'route_open_invalid'),
        ('tool-without-aid', 'route_tool_missing'),
    ],
)
async def test_a_repair_must_fit_the_rules(client: AsyncClient, me: dict, tools: dict, case: str, problem: str):
    lock = {'key': tools['tower_key']['id']}
    repairs = {
        'ability': {'ability': 'luck'},
        'difficulty': {'ability': 'str', 'difficulty': 'impossible'},
        'tool-without-aid': {'ability': 'str', 'needs_tool': True},
    }
    routes = [route(tools['gate'], tools['square'], lock=lock, repair=repairs[case])]
    # 락픽은 따기만 거든다. 고치기를 거드는 물건이 없다(#802)
    scenario = await route_doors.draft(client, me, tools, routes=routes, items=route_doors.the_items(tools))

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_as_no_repair():
    document = {'format': 54, 'routes': [{'from_place': 'a', 'to_place': 'b', 'force': None}]}

    upgraded = upgrade_from_54(document)

    assert upgraded['format'] == 55
    assert upgraded['routes'] == [{'from_place': 'a', 'to_place': 'b', 'force': None, 'repair': None}]
    assert 'repair' not in document['routes'][0]
    assert UPGRADES[54] is upgrade_from_54
    assert upgrade_from_54({'format': 54})['routes'] == []


# --- 맵 ---


async def test_the_map_shows_how_to_repair_and_whether_a_tool_is_needed(
    client: AsyncClient, me: dict, friend: dict, tools: dict
):
    table = await start(client, me, friend, tools)

    seen = await read_table(client, me, table)

    square = route_out(seen, tools['gate'], tools['square'])['repair']
    assert square == {'ability': 'dex', 'difficulty': 'hard', 'needs_tool': False}
    # 난이도를 비웠으면 규칙의 기본(보통)이다. 어느 물건이 거드는지는 판의 물건 목록에 있다
    forest = route_out(seen, tools['gate'], tools['forest'])['repair']
    assert forest == {'ability': 'str', 'difficulty': 'medium', 'needs_tool': True}
    assert route_out(seen, tools['gate'], tools['hut'])['repair'] is None


# --- 고치기 ---


async def test_a_broken_door_is_mended_with_the_tool_and_stays_open(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, tools: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, tools)
    await break_door(session, table, tools['gate'], tools['forest'])
    await give(session, table, ME, tools['hammer'])
    load_dice(app, [15])

    await play(client, me, friend, table, narrated, mine=door('repair', tools['forest'], item=tools['hammer']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['act'], outcome['device'], outcome['done'], outcome['reason']) == ('repair', None, True, None)
    assert (outcome['check']['ability'], outcome['check']['difficulty']) == ('str', 'medium')
    forest = route_out(await read_table(client, me, table), tools['gate'], tools['forest'])
    assert (forest['broken'], forest['barred']) == (False, False)
    (changed,) = await events_of(client, me, table, 'door_changed')
    assert (changed['payload']['act'], changed['payload']['device']) == ('repair', None)
    (rolled,) = await events_of(client, me, table, 'check_rolled')
    assert changed['caused_by_sequence'] == rolled['sequence']


async def test_a_mended_door_can_be_locked_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, tools: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, tools)
    await break_door(session, table, tools['gate'], tools['square'])
    await give(session, table, ME, tools['tower_key'])
    load_dice(app, [20])

    await play(client, me, friend, table, narrated, mine=door('repair', tools['square']))
    await play(client, me, friend, table, narrated, mine=door('lock', tools['square']))

    mended, locked = [await door_outcome(client, me, table, number) for number in (1, 2)]
    # 도구를 적지 않은 문은 맨손으로 고친다. 어려움(20)이라 20 이 나와야 한다
    assert (mended['done'], mended['check']['target']) == (True, 20)
    assert locked['done'] is True
    square = route_out(await read_table(client, me, table), tools['gate'], tools['square'])
    assert (square['broken'], square['locked']) == (False, True)


async def test_a_weak_try_leaves_the_door_broken(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, tools: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, tools)
    await break_door(session, table, tools['gate'], tools['forest'])
    await give(session, table, ME, tools['hammer'])
    load_dice(app, [14])

    await play(client, me, friend, table, narrated, mine=door('repair', tools['forest'], item=tools['hammer']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['reason'], outcome['check']['target']) == (False, 'failed', 15)
    assert route_out(await read_table(client, me, table), tools['gate'], tools['forest'])['broken'] is True
    assert await events_of(client, me, table, 'door_changed') == []
    assert len(await events_of(client, me, table, 'check_rolled')) == 1


@pytest.mark.parametrize('case', ['not-broken', 'no-tool'])
async def test_nothing_is_rolled_when_there_is_nothing_to_mend_or_nothing_to_mend_with(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, tools: dict, session: AsyncSession, narrated, case: str
):
    table = await start(client, me, friend, tools)
    await give(session, table, ME, tools['hammer'])
    if case == 'no-tool':
        await break_door(session, table, tools['gate'], tools['forest'])
    load_dice(app, [20])

    declared = await declare(client, me, table, door('repair', tools['forest'], item=tools['hammer']))
    # 받은 뒤 차례가 오기 전에 망치를 잃었다
    if case == 'no-tool':
        await take_away(session, table, ME, tools['hammer'])
    await play_theirs(client, friend, table, narrated)

    outcome = await door_outcome(client, me, table)
    reason = {'not-broken': 'already', 'no-tool': 'no_tool'}[case]
    assert declared.status_code == status.HTTP_200_OK, declared.text
    assert (outcome['done'], outcome['reason'], outcome['check']) == (False, reason, None)
    # 굴리지 않았으면 붙인 물건은 쓰지 않았다(#802)
    assert (outcome['aid']['used'], outcome['aid']['reason']) == (False, None if case == 'not-broken' else 'not_held')
    assert await events_of(client, me, table, 'check_rolled') == []


async def play_theirs(client: AsyncClient, friend: dict, table: dict, narrated) -> None:
    """함께 앉은 사람이 글만 내 라운드를 닫는다. 나는 이미 선언했다."""
    declared = await declare(client, friend, table, None)
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()


async def test_a_door_without_a_repair_cannot_be_mended(
    client: AsyncClient, me: dict, friend: dict, tools: dict, session: AsyncSession
):
    table = await start(client, me, friend, tools)

    response = await declare(client, me, table, door('repair', tools['hut']))

    assert (response.status_code, response.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_repairable')


async def test_a_door_can_be_mended_from_either_end(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, tools: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, tools)
    await break_door(session, table, tools['gate'], tools['forest'])
    await put_at(session, table, ME, tools['forest'])
    await give(session, table, ME, tools['hammer'])
    load_dice(app, [15])

    await play(client, me, friend, table, narrated, mine=door('repair', tools['gate'], item=tools['hammer']))

    assert (await door_outcome(client, me, table))['done'] is True


# --- 서술과 기록 ---


def test_the_repair_lines():
    mended = DoorNote(act='repair', other_end='숲', done=True, check='근력')
    slipped = DoorNote(act='repair', other_end='숲', done=False, reason='failed', check='근력')
    whole = DoorNote(act='repair', other_end='숲', done=False, reason='already')
    empty_handed = DoorNote(act='repair', other_end='숲', done=False, reason='no_tool')

    assert describe_door(mended) == '(문: 숲 쪽 문. 근력 판정에 성공해 부서진 문을 고쳤다)'
    assert describe_door(slipped) == '(문: 숲 쪽 문을 고치려 했다. 근력 판정에 실패했다)'
    assert describe_door(whole) == '(문: 숲 쪽 문을 고치려 했다. 부서진 문이 아니었다)'
    assert describe_door(empty_handed) == '(문: 숲 쪽 문을 고치려 했다. 고칠 도구가 없었다)'
    # 따기의 같은 까닭은 그대로다
    assert describe_door(DoorNote(act='pick', other_end='숲', done=False, reason='no_tool')).endswith(
        '딸 도구가 없었다)'
    )


def test_the_map_note_says_a_broken_door_is_mended_only_by_the_roll():
    assert "'부서진 문'은 고치는 판정에 성공해야 고쳐진다" in prompt.MAP_NOTE
    assert prompt.PROMPT_VERSION == 'narration-72'


def test_the_transcript_says_the_door_was_mended():
    payload = {**SAMPLES['door_changed'], 'act': 'repair', 'device': None}

    assert render_event(event('door_changed', payload), Labels()) == (
        '- 문: 드워프 기사 · 수로 입구 ↔ 깊은 수로 문 고침\n'
    )
