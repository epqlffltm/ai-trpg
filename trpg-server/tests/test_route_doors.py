# trpg-server/tests/test_route_doors.py

"""
길의 문을 다루는 것(#281)을 검증한다. 빗장, 잠그기와 열기, 따기, 부수기다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 시작은 성문.
여기에 물건 넷(탑 열쇠, 대장간 열쇠, 오두막 열쇠, 락픽)을 더하고 길을 이렇게 놓는다.
  - 성문-광장: 탑 열쇠의 자물쇠(잠김). 민첩으로 딴다(도구가 있어야 한다, 락픽이 따기를 거든다, #802).
    근력·어려움(20)으로 부순다.
  - 성문-숲: 숲 쪽의 빗장(걸림). 근력으로 부순다(난이도는 비워 보통 15).
  - 광장-탑: 대장간 열쇠의 자물쇠(열림). 따지도 부수지도 못한다.
  - 성문-오두막: 오두막 열쇠의 자물쇠(열림)와 성문 쪽의 빗장(안 걸림)이 다 있다.
시트의 능력치는 모두 10(보정 0)이다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 따기, 빗장, 부수기를 저장하고 판에 굳힌다. 잘못 둔 것은 422, 게시할 수 없는 것은 409 의 문제다.
    옛 판은 셋 다 없는 것으로 읽는다.
  - 맵: 빗장과 그 쪽, 부서졌는지, 따기와 부수기의 판정과 도구가 있어야 하는지가 보인다.
  - 가기: 빗장 쪽에서는 풀고 지나가고, 반대쪽에서는 막힌다.
  - 잠그기와 열기: 자물쇠는 열쇠로, 빗장은 빗장 쪽에서. 장치를 비우면 그 길의 하나로, 둘 다 있으면 적어야 한다.
  - 따기: 도구를 붙여야 굴리고, 성공하면 열린다. 부수기: 성공하면 문이 부서져 열리고 다시 잠그지 못한다.
  - 이벤트: 해낸 것만 door_changed, 굴린 것은 check_rolled. 서술: 한 일의 줄과 나가는 길의 표시.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_52
from app.engine.templates import SRD5
from app.rounds.move_lines import describe_door, describe_travel
from app.rounds.narration_request import to_door, to_travel
from app.rounds.narrator import DoorNote, TravelNote
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import going, outcome_of, play
from tests.test_table_items import ME, SCENARIOS_URL, events_of, give, post, read_table, table_url
from tests.test_table_map import open_duo, place_of, put_at, route
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore


@pytest.fixture
async def gear(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 물건 넷(탑 열쇠, 대장간 열쇠, 오두막 열쇠, 락픽)을 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {
        **lore,
        'tower_key': await entry('탑 열쇠'),
        'forge_key': await entry('대장간 열쇠'),
        'hut_key': await entry('오두막 열쇠'),
        'lockpick': await entry('락픽'),
    }


def the_routes(gear: dict) -> list[dict]:
    pick = {'ability': 'dex', 'needs_tool': True}
    return [
        route(
            gear['gate'],
            gear['square'],
            lock={'key': gear['tower_key']['id'], 'pick': pick},
            force={'ability': 'str', 'difficulty': 'hard'},
        ),
        route(
            gear['gate'], gear['forest'], bar={'side': gear['forest']['id'], 'barred': True}, force={'ability': 'str'}
        ),
        route(gear['square'], gear['tower'], lock={'key': gear['forge_key']['id'], 'locked': False}),
        route(
            gear['gate'],
            gear['hut'],
            lock={'key': gear['hut_key']['id'], 'locked': False},
            bar={'side': gear['gate']['id']},
        ),
    ]


def the_items(gear: dict) -> list[dict]:
    """락픽은 따기를 거든다(#802). 보정이 없고 없어지지 않는다(예전의 따는 도구와 같다)."""
    return [{'entry_id': gear['lockpick']['id'], 'aids': [{'act': 'pick'}]}]


def the_map(gear: dict) -> dict:
    return {'start_place': gear['gate']['id'], 'routes': the_routes(gear), 'items': the_items(gear)}


async def draft(client: AsyncClient, me: dict, gear: dict, **fields) -> dict:
    """문을 적은 시나리오. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [gear['lorebook']['id']],
        **the_map(gear),
        **fields,
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, friend: dict, gear: dict) -> dict:
    """문을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, gear, **the_map(gear))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def route_out(table: dict, start: dict, end: dict) -> dict:
    """테이블이 아는 맵에서 그 두 끝의 길."""
    return next(
        item for item in table['map']['routes'] if (item['from_place'], item['to_place']) == (start['id'], end['id'])
    )


def door(act: str, place: dict, device: str | None = None, item: dict | None = None) -> dict:
    action = {'kind': act, 'place': place['id']}
    if item is not None:
        action['item'] = item['id']
    return action if device is None else {**action, 'device': device}


async def declare(client: AsyncClient, headers: dict, table: dict, action: dict):
    body = {'content': '문으로 간다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def door_outcome(client: AsyncClient, me: dict, table: dict, number: int = 1) -> dict:
    return (await outcome_of(client, me, table, number, ME))['door']


# --- 시나리오 ---


async def test_doors_are_saved_and_published(client: AsyncClient, me: dict, gear: dict):
    scenario = await draft(client, me, gear)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    square, forest, _, hut = scenario['routes']
    assert square['lock']['pick'] == {'ability': 'dex', 'difficulty': None, 'needs_tool': True}
    assert (square['force'], square['bar']) == ({'ability': 'str', 'difficulty': 'hard'}, None)
    assert forest['bar'] == {'side': gear['forest']['id'], 'barred': True}
    assert hut['bar'] == {'side': gear['gate']['id'], 'barred': False}
    routes = read_snapshot(response.json()['snapshot']).routes
    assert routes[0].lock.pick.needs_tool is True
    assert (routes[1].bar.side, routes[1].bar.barred, routes[1].force.ability) == (
        uuid.UUID(gear['forest']['id']),
        True,
        'str',
    )


@pytest.mark.parametrize('case', ['bar-elsewhere', 'force-without-door', 'pick-unknown-field'])
async def test_a_misshaped_door_is_refused(client: AsyncClient, me: dict, gear: dict, case: str):
    fields = {
        'bar-elsewhere': {'bar': {'side': gear['tower']['id']}},
        'force-without-door': {'force': {'ability': 'str'}},
        'pick-unknown-field': {'lock': {'key': gear['tower_key']['id'], 'pick': {'ability': 'dex', 'noise': 1}}},
    }
    body = {'title': '성의 모험', 'routes': [route(gear['gate'], gear['square'], **fields[case])]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('pick-ability', 'route_open_invalid'),
        ('force-difficulty', 'route_open_invalid'),
        ('tool-without-aid', 'route_tool_missing'),
    ],
)
async def test_a_door_must_fit_the_rules(client: AsyncClient, me: dict, gear: dict, case: str, problem: str):
    lock = {'key': gear['tower_key']['id']}
    fields = {
        'pick-ability': {'lock': {**lock, 'pick': {'ability': 'luck'}}},
        'force-difficulty': {'lock': lock, 'force': {'ability': 'str', 'difficulty': 'impossible'}},
        'tool-without-aid': {'lock': {**lock, 'pick': {'ability': 'dex', 'needs_tool': True}}},
    }
    routes = [route(gear['gate'], gear['square'], **fields[case])]
    # 도구가 있어야 하는 문을 거들 물건이 없다(#802)
    scenario = await draft(client, me, gear, routes=routes, items=[])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_a_door_s_old_tool_is_refused(client: AsyncClient, me: dict, gear: dict):
    # 특정 도구(tool)는 도구가 있어야 하는가(needs_tool)와 물건의 거들기가 됐다(#802)
    lock = {'key': gear['tower_key']['id'], 'pick': {'ability': 'dex', 'tool': gear['lockpick']['id']}}
    body = {'title': '성의 모험', 'routes': [route(gear['gate'], gear['square'], lock=lock)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_an_old_snapshot_reads_as_no_other_ways_to_open():
    locked = {'from_place': 'a', 'to_place': 'b', 'lock': {'key': 'k', 'locked': True}}
    plain = {'from_place': 'b', 'to_place': 'c', 'lock': None}
    document = {'format': 52, 'routes': [locked, plain]}

    upgraded = upgrade_from_52(document)

    assert upgraded['format'] == 53
    assert upgraded['routes'] == [
        {**locked, 'lock': {'key': 'k', 'locked': True, 'pick': None}, 'bar': None, 'force': None},
        {**plain, 'bar': None, 'force': None},
    ]
    assert 'bar' not in document['routes'][0]
    assert UPGRADES[52] is upgrade_from_52
    assert upgrade_from_52({'format': 52})['routes'] == []


# --- 맵 ---


async def test_the_map_shows_bars_breaks_and_ways_to_open(client: AsyncClient, me: dict, friend: dict, gear: dict):
    table = await start(client, me, friend, gear)

    square = route_out(table, gear['gate'], gear['square'])
    assert (square['locked'], square['barred'], square['bar_side'], square['broken']) == (True, None, None, False)
    # 따는 판정과 도구가 있어야 하는지가 보인다(#802). 어느 물건이 거드는지는 판의 물건 목록에 있다
    assert square['pick'] == {'ability': 'dex', 'difficulty': 'medium', 'needs_tool': True}
    assert square['force'] == {'ability': 'str', 'difficulty': 'hard'}
    forest = route_out(table, gear['gate'], gear['forest'])
    assert (forest['locked'], forest['barred'], forest['bar_side']) == (None, True, gear['forest']['id'])
    assert route_out(table, gear['square'], gear['tower'])['pick'] is None


# --- 가기와 빗장 ---


async def test_a_bar_stops_those_on_the_other_side(client: AsyncClient, me: dict, friend: dict, gear: dict, narrated):
    table = await start(client, me, friend, gear)

    await play(client, me, friend, table, narrated, mine=going(gear['forest']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['reason'], move['unbarred']) == (False, 'barred', False)


async def test_one_on_the_bar_side_lifts_it_and_goes(
    client: AsyncClient, me: dict, friend: dict, gear: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, gear)
    await put_at(session, table, ME, gear['forest'])

    await play(client, me, friend, table, narrated, mine=going(gear['gate']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['unbarred']) == (True, True)
    seen = await read_table(client, me, table)
    assert (place_of(seen, ME), route_out(seen, gear['gate'], gear['forest'])['barred']) == (gear['gate']['id'], False)
    (moved,) = await events_of(client, me, table, 'character_moved')
    assert moved['payload']['unbarred'] is True


# --- 잠그기와 열기 ---


async def test_a_bar_is_set_and_lifted_from_its_side(client: AsyncClient, me: dict, friend: dict, gear: dict, narrated):
    table = await start(client, me, friend, gear)

    await play(client, me, friend, table, narrated, mine=door('lock', gear['hut'], 'bar'))
    await play(client, me, friend, table, narrated, mine=door('lock', gear['hut'], 'bar'))
    await play(client, me, friend, table, narrated, mine=door('unlock', gear['hut'], 'bar'))

    first, again, lifted = [await door_outcome(client, me, table, number) for number in (1, 2, 3)]
    assert (first['done'], first['act'], first['device'], first['check']) == (True, 'lock', 'bar', None)
    assert (again['done'], again['reason']) == (False, 'already')
    assert lifted['done'] is True
    assert route_out(await read_table(client, me, table), gear['gate'], gear['hut'])['barred'] is False
    barred, unbarred = await events_of(client, me, table, 'door_changed')
    assert barred['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '기사',
        'act': 'lock',
        'device': 'bar',
        'from': {'entry_id': gear['gate']['id'], 'name': '성문'},
        'to': {'entry_id': gear['hut']['id'], 'name': '오두막'},
    }
    assert unbarred['payload']['act'] == 'unlock'


async def test_a_bar_cannot_be_reached_from_the_other_side(
    client: AsyncClient, me: dict, friend: dict, gear: dict, narrated
):
    table = await start(client, me, friend, gear)

    await play(client, me, friend, table, narrated, mine=door('unlock', gear['forest']))

    outcome = await door_outcome(client, me, table)
    # 장치를 비웠다. 그 길에는 빗장 하나뿐이라 빗장으로 채운다
    assert (outcome['device'], outcome['done'], outcome['reason']) == ('bar', False, 'wrong_side')


async def test_a_lock_needs_its_key_to_turn(
    client: AsyncClient, me: dict, friend: dict, gear: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, gear)
    await put_at(session, table, ME, gear['square'])

    await play(client, me, friend, table, narrated, mine=door('lock', gear['tower']))
    await give(session, table, ME, gear['forge_key'])
    await play(client, me, friend, table, narrated, mine=door('lock', gear['tower']))
    await play(client, me, friend, table, narrated, mine=door('unlock', gear['tower']))

    keyless, locked, opened = [await door_outcome(client, me, table, number) for number in (1, 2, 3)]
    assert (keyless['done'], keyless['reason'], keyless['device']) == (False, 'no_key', 'lock')
    assert (locked['done'], opened['done']) == (True, True)
    assert route_out(await read_table(client, me, table), gear['square'], gear['tower'])['locked'] is False


async def test_a_broken_lock_does_not_turn_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, gear: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, gear)
    await give(session, table, ME, gear['tower_key'])
    load_dice(app, [20])

    await play(client, me, friend, table, narrated, mine=door('unlock', gear['square']))
    await play(client, me, friend, table, narrated, mine=door('unlock', gear['square']))
    await play(client, me, friend, table, narrated, mine=door('lock', gear['square']))
    await play(client, me, friend, table, narrated, mine=door('lock', gear['square']))
    await play(client, me, friend, table, narrated, mine=door('force', gear['square']))
    await play(client, me, friend, table, narrated, mine=door('lock', gear['square']))

    opened, again, locked, twice, forced, relock = [
        await door_outcome(client, me, table, number) for number in range(1, 7)
    ]
    assert (opened['done'], again['reason'], locked['done'], twice['reason']) == (True, 'already', True, 'already')
    assert forced['done'] is True
    # 열쇠가 있어도 부서진 자물쇠는 잠기지 않는다
    assert (relock['done'], relock['reason']) == (False, 'broken')
    square = route_out(await read_table(client, me, table), gear['gate'], gear['square'])
    assert (square['locked'], square['broken']) == (False, True)


async def test_the_device_must_be_named_when_there_are_two(client: AsyncClient, me: dict, friend: dict, gear: dict):
    table = await start(client, me, friend, gear)

    both = await declare(client, me, table, door('lock', gear['hut']))
    absent = await declare(client, me, table, door('lock', gear['forest'], 'lock'))
    no_door = await declare(client, me, table, door('pick', gear['tower']))
    far = await declare(client, me, table, door('lock', gear['cellar']))

    assert both.status_code == absent.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert both.json()['detail'].startswith('action.device')
    assert far.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert far.json()['detail'].startswith('action.place')
    # 광장-탑은 성문에 닿지 않는다
    assert no_door.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 따기와 부수기 ---


async def test_picking_needs_the_tool_and_a_good_roll(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, gear: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, gear)
    pick = door('pick', gear['square'], item=gear['lockpick'])

    toolless = await declare(client, me, table, door('pick', gear['square']))
    unheld = await declare(client, me, table, pick)
    await give(session, table, ME, gear['lockpick'])
    load_dice(app, [5, 15])
    await play(client, me, friend, table, narrated, mine=pick)
    await play(client, me, friend, table, narrated, mine=pick)
    await play(client, me, friend, table, narrated, mine=pick)

    slipped, picked, again = [await door_outcome(client, me, table, number) for number in (1, 2, 3)]
    # 도구가 있어야 하는데 붙이지 않았거나 지니지 않았으면 받지 않는다(#802)
    assert (toolless.status_code, unheld.status_code) == (422, 409)
    # 열린 자물쇠는 굴리지 않는다. 락픽은 없어지지 않는다
    assert (again['done'], again['reason'], again['check']) == (False, 'already', None)
    assert again['aid']['used'] is False
    assert (slipped['done'], slipped['reason'], slipped['check']['roll']) == (False, 'failed', 5)
    assert (slipped['aid']['used'], slipped['aid']['lost'], slipped['aid']['remaining']) == (True, False, 1)
    assert (picked['done'], picked['check']['ability'], picked['check']['difficulty']) == (True, 'dex', 'medium')
    assert route_out(await read_table(client, me, table), gear['gate'], gear['square'])['locked'] is False
    assert len(await events_of(client, me, table, 'check_rolled')) == 2
    (opened,) = await events_of(client, me, table, 'door_changed')
    assert (opened['payload']['act'], opened['payload']['device']) == ('pick', None)


async def test_forcing_breaks_the_door_for_good(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, gear: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, gear)
    load_dice(app, [15])

    await play(client, me, friend, table, narrated, mine=door('force', gear['forest']))
    await play(client, me, friend, table, narrated, mine=door('force', gear['forest']))
    await put_at(session, table, ME, gear['forest'])
    await play(client, me, friend, table, narrated, mine=door('lock', gear['gate'], 'bar'))

    forced, again, barring = [await door_outcome(client, me, table, number) for number in (1, 2, 3)]
    assert (forced['done'], forced['check']['difficulty']) == (True, 'medium')
    # 부서진 문은 열려 있다. 부술 것이 없어 굴리지 않는다
    assert (again['done'], again['reason'], again['check']) == (False, 'already', None)
    assert (barring['done'], barring['reason']) == (False, 'broken')
    forest = route_out(await read_table(client, me, table), gear['gate'], gear['forest'])
    assert (forest['broken'], forest['barred']) == (True, False)


async def test_a_weak_blow_leaves_the_door(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, gear: dict, narrated
):
    table = await start(client, me, friend, gear)
    load_dice(app, [19])

    await play(client, me, friend, table, narrated, mine=door('force', gear['square']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['reason'], outcome['check']['target']) == (False, 'failed', 20)
    assert route_out(await read_table(client, me, table), gear['gate'], gear['square'])['locked'] is True


async def test_a_door_without_a_way_cannot_be_picked_or_forced(
    client: AsyncClient, me: dict, friend: dict, gear: dict, session: AsyncSession
):
    table = await start(client, me, friend, gear)
    await put_at(session, table, ME, gear['square'])

    picking = await declare(client, me, table, door('pick', gear['tower']))
    forcing = await declare(client, me, table, door('force', gear['tower']))

    assert (picking.status_code, picking.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_pickable')
    assert (forcing.status_code, forcing.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_forceable')


# --- 서술 ---


async def test_the_narrator_hears_the_doors(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, gear: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, gear)
    load_dice(app, [15])

    await play(client, me, friend, table, narrated, mine=door('force', gear['forest']))

    (request,) = narrator.requests
    knight = next(move for move in request.moves if move.character_name == '기사')
    assert knight.door == DoorNote(act='force', other_end='숲', done=True, check='근력')
    assert knight.place.exits == ['광장(잠긴 문)', '숲(부서진 문)', '오두막']


def test_the_door_lines():
    barred = DoorNote(act='lock', other_end='창고', done=True, device='bar')
    picked = DoorNote(act='pick', other_end='탑', done=True, check='민첩')
    slipped = DoorNote(act='pick', other_end='탑', done=False, reason='failed', check='민첩')
    keyless = DoorNote(act='unlock', other_end='탑', done=False, device='lock', reason='no_key')

    assert describe_door(barred) == '(문: 창고 쪽 문. 빗장을 걸었다)'
    assert describe_door(picked) == '(문: 탑 쪽 문. 민첩 판정에 성공해 자물쇠를 땄다)'
    assert describe_door(slipped) == '(문: 탑 쪽 문을 따려 했다. 민첩 판정에 실패했다)'
    assert describe_door(keyless) == '(문: 탑 쪽 문을 열려 했다. 맞는 열쇠가 없었다)'


def test_the_travel_line_tells_the_bar():
    lifted = TravelNote(from_place='숲', to_place='성문', moved=True, unbarred=True)
    stopped = TravelNote(from_place='성문', to_place='숲', moved=False, reason='barred')

    assert describe_travel(lifted) == '(간 곳: 숲 → 성문, 빗장을 풀고)'
    assert describe_travel(stopped) == '(가려던 곳: 숲. 반대쪽에 빗장이 걸려 있었다)'


def test_the_door_note_is_read_from_the_outcome():
    outcome = {
        'door': {
            'to': {'entry_id': str(uuid.uuid4()), 'name': '탑'},
            'act': 'pick',
            'device': None,
            'done': False,
            'reason': 'failed',
            'check': {'ability': 'dex'},
        }
    }

    assert to_door(SimpleNamespace(outcome=outcome), SRD5) == DoorNote(
        act='pick', other_end='탑', done=False, reason='failed', check='민첩'
    )
    assert to_door(SimpleNamespace(outcome={'move': {}}), SRD5) is None


def test_the_travel_note_hears_a_lifted_bar():
    move = {
        'from': {'entry_id': str(uuid.uuid4()), 'name': '숲'},
        'to': {'entry_id': str(uuid.uuid4()), 'name': '성문'},
        'moved': True,
        'reason': None,
        'unbarred': True,
        'unlocked': False,
        'cross': None,
        'effect': None,
    }

    assert to_travel(SimpleNamespace(outcome={'move': move}), SRD5).unbarred is True
