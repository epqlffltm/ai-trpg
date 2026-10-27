# trpg-server/tests/test_route_door_happenings.py

"""
판의 사건이 길의 문을 다루는 것(#281, app/rounds/happenings.py)을 검증한다. 잠그기, 열기, 고치기다.

맵과 물건은 tests/test_route_doors.py 의 것이다. 시작은 성문이고 길은 이렇다.
  - 성문-광장: 탑 열쇠의 자물쇠(잠김). 부술 수 있다.
  - 성문-숲: 숲 쪽의 빗장(걸림).
  - 광장-탑: 대장간 열쇠의 자물쇠(열림).
  - 성문-오두막: 오두막 열쇠의 자물쇠(열림)와 성문 쪽의 빗장(안 걸림).
여기에 사건 항목 둘(경비 교대, 수리공)을 더한다. 사건은 성문에 닿으면(시작부터) 첫 라운드가 닫힐 때 일어난다.

보는 것.
  - 시나리오: 문을 다루는 효과를 저장하고 판에 굳힌다. 모양이 틀리면 422, 다룰 문이 없으면 409 의 문제다.
    옛 판은 장치가 없는 것으로 읽는다.
  - 라운드: 장치를 비우면 그 문의 장치 모두를, 적으면 그것만 다룬다. 길의 방향은 보지 않는다.
    부서진 문은 잠그지 않고, 고친 뒤에는 잠근다. 이미 그런 장치는 적지 않는다. 문의 상태가 없는 테이블은 그대로다.
    다룬 문은 사건의 줄에만 적고 이벤트는 내지 않는다.
  - 서술: 일행이 그 길의 끝에 있을 때만 다룬 문이 일어난 사건의 줄에 붙는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_53
from app.rounds import prompt
from app.rounds.narration_request import describe_happening_door
from app.rounds.narrator import HappeningNote
from tests import test_route_doors as route_doors
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_map_actions import play
from tests.test_table_items import SCENARIOS_URL, events_of, post, read_table, table_url
from tests.test_table_map import open_duo, route
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
gear = route_doors.gear
route_out = route_doors.route_out


@pytest.fixture
async def doors(client: AsyncClient, me: dict, gear: dict) -> dict:
    """같은 로어북에 사건 항목 둘(경비 교대, 수리공)을 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{gear["lorebook"]["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='event')

    return {**gear, 'watch': await entry('경비 교대'), 'mender': await entry('수리공')}


def door_effect(kind: str, one: dict, other: dict, device: str | None = None) -> dict:
    """문을 다루는 효과. 길의 두 끝과, 적으면 장치다."""
    effect = {'kind': kind, 'from_place': one['id'], 'to_place': other['id']}
    return effect if device is None else {**effect, 'device': device}


def at_gate(doors: dict, entry: dict, effects: list[dict]) -> dict:
    """성문에 닿으면(시작부터) 일어나는 사건."""
    return {
        'entry_id': entry['id'],
        'when': [{'kind': 'reach_place', 'target': doors['gate']['id']}],
        'effects': effects,
    }


async def draft(client: AsyncClient, me: dict, doors: dict, happenings: list[dict], **fields) -> dict:
    return await route_doors.draft(client, me, doors, happenings=happenings, **fields)


async def start(client: AsyncClient, me: dict, friend: dict, doors: dict, happenings: list[dict]) -> dict:
    """그 사건들과 문을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, doors, **route_doors.the_map(doors), happenings=happenings)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def doors_written(session: AsyncSession, table: dict) -> list[dict]:
    """그 테이블에서 일어난 사건들이 다룬 문. 일어난 차례다."""
    rows = await session.execute(
        text('SELECT doors FROM table_happenings WHERE table_id = :table_id ORDER BY created_at'),
        {'table_id': table['id']},
    )
    return [change for (changes,) in rows for change in changes]


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


def change(act: str, one: dict, other: dict, device: str | None) -> dict:
    return {'act': act, 'device': device, 'from': one['id'], 'to': other['id']}


# --- 시나리오 ---


async def test_door_effects_are_saved_and_published(client: AsyncClient, me: dict, doors: dict):
    effects = [
        door_effect('lock_route', doors['hut'], doors['gate']),
        door_effect('unlock_route', doors['gate'], doors['forest'], 'bar'),
        door_effect('repair_route', doors['gate'], doors['square']),
    ]
    scenario = await draft(client, me, doors, [at_gate(doors, doors['watch'], effects)])

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['happenings'][0]['effects'] == [
        {'kind': 'lock_route', 'from_place': doors['hut']['id'], 'to_place': doors['gate']['id'], 'device': None},
        {'kind': 'unlock_route', 'from_place': doors['gate']['id'], 'to_place': doors['forest']['id'], 'device': 'bar'},
        {'kind': 'repair_route', 'from_place': doors['gate']['id'], 'to_place': doors['square']['id']},
    ]
    (rule,) = read_snapshot(response.json()['snapshot']).happenings
    assert [(effect.kind, effect.device) for effect in rule.effects] == [
        ('lock_route', None),
        ('unlock_route', 'bar'),
        ('repair_route', None),
    ]


@pytest.mark.parametrize('case', ['same-ends', 'unknown-device', 'repair-with-device', 'no-end'])
async def test_a_misshaped_door_effect_is_refused(client: AsyncClient, me: dict, doors: dict, case: str):
    effects = {
        'same-ends': door_effect('lock_route', doors['gate'], doors['gate']),
        'unknown-device': door_effect('lock_route', doors['gate'], doors['hut'], 'chain'),
        'repair-with-device': door_effect('repair_route', doors['gate'], doors['hut'], 'lock'),
        'no-end': {'kind': 'unlock_route', 'to_place': doors['hut']['id']},
    }
    body = {'title': '성의 모험', 'happenings': [at_gate(doors, doors['watch'], [effects[case]])]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize('case', ['no-route', 'off-map', 'no-door', 'no-such-device'])
async def test_a_door_effect_needs_a_door(client: AsyncClient, me: dict, doors: dict, case: str):
    effects = {
        # 성문과 탑 사이에는 길이 없다
        'no-route': door_effect('lock_route', doors['gate'], doors['tower']),
        # 지하실은 맵에 없다. 옮기는 효과가 아니므로 맵 밖의 장소(happening_place_off_map)로는 보지 않는다
        'off-map': door_effect('unlock_route', doors['gate'], doors['cellar']),
        'no-door': door_effect('repair_route', doors['tower'], doors['cellar']),
        # 성문-숲에는 빗장뿐이다
        'no-such-device': door_effect('lock_route', doors['forest'], doors['gate'], 'lock'),
    }
    # 문이 없는 길(탑-지하실)은 그 경우에만 둔다
    plain = [route(doors['tower'], doors['cellar'])] if case == 'no-door' else []
    routes = [*route_doors.the_routes(doors), *plain]
    scenario = await draft(client, me, doors, [at_gate(doors, doors['watch'], [effects[case]])], routes=routes)

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['happening_route_invalid']


@pytest.mark.parametrize('case', ['no-such-device', 'no-door'])
async def test_the_snapshot_refuses_a_door_effect_without_a_door(client: AsyncClient, me: dict, doors: dict, case: str):
    effect = door_effect('lock_route', doors['gate'], doors['forest'])
    scenario = await draft(client, me, doors, [at_gate(doors, doors['watch'], [effect])])
    document = (await route_doors.publish(client, me, scenario)).json()['snapshot']
    (rule,) = document['happenings']
    square, forest, *rest = document['routes']
    wrong = {
        # 성문-숲에는 빗장뿐이다
        'no-such-device': {
            **document,
            'happenings': [{**rule, 'effects': [{**rule['effects'][0], 'device': 'lock'}]}],
        },
        # 빗장을 떼면 성문-숲에는 문이 없다. 장치를 비운 효과도 다룰 것이 없다
        'no-door': {**document, 'routes': [square, {**forest, 'bar': None}, *rest]},
    }

    with pytest.raises(ValidationError):
        Snapshot.model_validate(wrong[case])
    Snapshot.model_validate(document)


def test_an_old_snapshot_reads_as_no_door_devices():
    moving = {'kind': 'move', 'to_place': 'a', 'from_place': None, 'npc': None}
    document = {'format': 53, 'happenings': [{'entry_id': 'e', 'when': [], 'effects': [moving]}]}

    upgraded = upgrade_from_53(document)

    assert upgraded['format'] == 54
    assert upgraded['happenings'][0]['effects'] == [{**moving, 'device': None}]
    assert 'device' not in document['happenings'][0]['effects'][0]
    assert UPGRADES[53] is upgrade_from_53
    assert upgrade_from_53({'format': 53})['happenings'] == []


# --- 라운드 ---


async def test_locking_with_no_device_shuts_every_part_of_the_door(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    # 길은 성문→오두막으로 적혔다. 효과는 반대 차례로 적어도 같은 길이다
    effects = [door_effect('lock_route', doors['hut'], doors['gate'])]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['watch'], effects)])

    await play(client, me, friend, table, narrated)

    hut = route_out(await read_table(client, me, table), doors['gate'], doors['hut'])
    assert (hut['locked'], hut['barred'], hut['broken']) == (True, True, False)
    assert await doors_written(session, table) == [
        change('lock', doors['hut'], doors['gate'], 'lock'),
        change('lock', doors['hut'], doors['gate'], 'bar'),
    ]
    # 다룬 문은 이벤트로 내지 않는다. 사건은 옮긴 사람 없이 적힌다
    assert await events_of(client, me, table, 'door_changed') == []
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    assert occurred['payload']['moves'] == []


async def test_a_named_device_is_the_only_one_touched(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    effects = [
        door_effect('unlock_route', doors['forest'], doors['gate'], 'bar'),
        door_effect('lock_route', doors['gate'], doors['hut'], 'bar'),
    ]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['watch'], effects)])

    await play(client, me, friend, table, narrated)

    seen = await read_table(client, me, table)
    assert route_out(seen, doors['gate'], doors['forest'])['barred'] is False
    hut = route_out(seen, doors['gate'], doors['hut'])
    assert (hut['locked'], hut['barred']) == (False, True)
    assert await doors_written(session, table) == [
        change('unlock', doors['forest'], doors['gate'], 'bar'),
        change('lock', doors['gate'], doors['hut'], 'bar'),
    ]


async def test_what_is_already_so_is_not_written(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    # 광장-탑의 자물쇠는 열려 있고, 성문-오두막의 문은 부서지지 않았다
    effects = [
        door_effect('unlock_route', doors['square'], doors['tower']),
        door_effect('repair_route', doors['gate'], doors['hut']),
    ]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['watch'], effects)])

    await play(client, me, friend, table, narrated)

    assert await doors_written(session, table) == []
    assert len(await events_of(client, me, table, 'happening_occurred')) == 1


async def test_a_broken_door_is_locked_only_after_it_is_mended(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    effects = [
        door_effect('lock_route', doors['gate'], doors['square']),
        door_effect('repair_route', doors['gate'], doors['square']),
        door_effect('lock_route', doors['gate'], doors['square']),
    ]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['mender'], effects)])
    await break_door(session, table, doors['gate'], doors['square'])

    await play(client, me, friend, table, narrated)

    square = route_out(await read_table(client, me, table), doors['gate'], doors['square'])
    assert (square['locked'], square['broken']) == (True, False)
    # 앞의 잠그기는 부서진 문이라 하지 못했다
    assert await doors_written(session, table) == [
        change('repair', doors['gate'], doors['square'], None),
        change('lock', doors['gate'], doors['square'], 'lock'),
    ]


async def test_a_mended_door_stays_open(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    effects = [door_effect('repair_route', doors['square'], doors['gate'])]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['mender'], effects)])
    await break_door(session, table, doors['gate'], doors['square'])

    await play(client, me, friend, table, narrated)

    square = route_out(await read_table(client, me, table), doors['gate'], doors['square'])
    assert (square['locked'], square['broken']) == (False, False)


async def test_a_table_without_door_states_is_left_alone(
    client: AsyncClient, me: dict, friend: dict, doors: dict, session: AsyncSession, narrated
):
    effects = [door_effect('lock_route', doors['gate'], doors['hut'])]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['watch'], effects)])
    # 문이 생기기 전에 시작한 테이블처럼 문의 상태가 없다
    await session.execute(text('DELETE FROM table_route_locks WHERE table_id = :table_id'), {'table_id': table['id']})
    await session.commit()

    await play(client, me, friend, table, narrated)

    assert await doors_written(session, table) == []
    assert len(await events_of(client, me, table, 'happening_occurred')) == 1


# --- 서술 ---


async def test_the_narrator_hears_only_the_doors_the_party_stands_by(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, doors: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    effects = [
        # 일행은 성문에 있다. 성문-숲의 빗장은 보이고, 광장-탑의 자물쇠는 아무도 보지 못한다
        door_effect('unlock_route', doors['gate'], doors['forest']),
        door_effect('lock_route', doors['tower'], doors['square']),
    ]
    table = await start(client, me, friend, doors, [at_gate(doors, doors['watch'], effects)])

    await play(client, me, friend, table, narrated)

    (request,) = narrator.requests
    assert request.happenings == [HappeningNote(name='경비 교대', doors=['성문 ↔ 숲 빗장 풀림'])]


@pytest.mark.parametrize(
    ('act', 'device', 'words'),
    [
        ('lock', 'lock', '자물쇠 잠김'),
        ('lock', 'bar', '빗장 걸림'),
        ('unlock', 'lock', '자물쇠 열림'),
        ('unlock', 'bar', '빗장 풀림'),
        ('repair', None, '부서진 문 고쳐짐'),
    ],
)
def test_a_door_change_is_told_by_its_ends_and_state(act: str, device: str | None, words: str):
    one, other = uuid.uuid4(), uuid.uuid4()
    places = {one: '성문', other: '광장'}

    told = describe_happening_door({'act': act, 'device': device, 'from': str(one), 'to': str(other)}, places)

    assert told == f'성문 ↔ 광장 {words}'


def test_the_prompt_puts_the_doors_after_those_moved():
    lines = prompt.happening_lines(
        [
            HappeningNote('습격', ['기사 → 탑'], ['성문 ↔ 광장 빗장 걸림']),
            HappeningNote('경비 교대', doors=['성문 ↔ 숲 자물쇠 잠김']),
        ]
    )

    assert lines[2:4] == ['- 습격: 기사 → 탑, 성문 ↔ 광장 빗장 걸림', '- 경비 교대: 성문 ↔ 숲 자물쇠 잠김']
    assert '잠기거나 열린 문은 장면이 끝날 때 그 상태다' in prompt.HAPPENING_NOTE
    assert prompt.PROMPT_VERSION == 'narration-75'
