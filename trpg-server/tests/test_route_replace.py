# trpg-server/tests/test_route_replace.py

"""
문의 자물쇠를 바꿔 다는 것(#281, 행동 '바꾸기')을 검증한다.

맵과 물건은 tests/test_route_doors.py 의 것이다. 시작은 성문이다. 여기에 물건 넷을 더한다.
  - 새 자물쇠: 새 열쇠로 연다. 민첩·어려움(20)으로 딴다(도구 없이).
  - 맹꽁이 자물쇠: 맹꽁이 열쇠로 연다. 따지 못한다.
  - 새 열쇠, 맹꽁이 열쇠: 위 두 자물쇠의 열쇠다.
길은 route_doors 의 것 그대로다. 성문-광장(탑 열쇠, 잠김, 락픽으로 딴다), 성문-숲(빗장만), 광장-탑(대장간 열쇠, 열림),
성문-오두막(오두막 열쇠, 열림, 빗장). 시트의 능력치는 모두 10(보정 0)이다.

보는 것.
  - 시나리오: 물건의 자물쇠를 저장하고 판에 굳힌다. 소모품이거나 자기 자신이 열쇠면 422,
    규칙에 없는 따는 판정은 409 item_lock_invalid, 다른 자물쇠와 같은 열쇠는 route_key_repeated,
    열쇠가 물건이 아니면 item_not_item 이다. 옛 판은 자물쇠 물건이 없는 것으로 읽는다.
  - 바꾸기: 판에 자물쇠가 있던 문에만(아니면 409 not_replaceable), 자물쇠 물건을(아니면 422 item), 지녀야(409) 한다.
    바꾸면 열린 채이고 자물쇠 물건이 없어진다. 그 뒤로는 새 열쇠만 잠그고 열고 지나가며, 따기는 새 자물쇠의 판정이다.
    부서진 문(broken), 잠긴 자물쇠(locked), 이미 단 자물쇠 물건(used), 그사이 없어진 물건(no_item)은 바꾸지 못한다.
  - 이벤트와 서술: 해낸 것만 door_changed(act replace). 굴리지 않는다. 한 일의 줄과 기록의 글.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_55
from app.rounds import prompt
from app.rounds.move_lines import describe_door
from app.rounds.narrator import DoorNote
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests import test_route_doors as route_doors
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import going, outcome_of, play
from tests.test_route_repair import break_door
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, give, held, post, read_table, table_url, take
from tests.test_table_map import open_duo, place_of, put_at
from tests.test_transcript_markdown import event
from tests.transcript_samples import SAMPLES

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
gear = route_doors.gear
declare = route_doors.declare
door_outcome = route_doors.door_outcome
route_out = route_doors.route_out


@pytest.fixture
async def locks(client: AsyncClient, me: dict, gear: dict) -> dict:
    """같은 로어북에 물건 넷(새 자물쇠, 새 열쇠, 맹꽁이 자물쇠, 맹꽁이 열쇠)을 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{gear["lorebook"]["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {
        **gear,
        'new_lock': await entry('새 자물쇠'),
        'new_key': await entry('새 열쇠'),
        'padlock': await entry('맹꽁이 자물쇠'),
        'padlock_key': await entry('맹꽁이 열쇠'),
    }


def the_items(locks: dict) -> list[dict]:
    """자물쇠 물건 둘. 새 자물쇠는 딸 수 있고, 맹꽁이 자물쇠는 따지 못한다."""
    return [
        {
            'entry_id': locks['new_lock']['id'],
            'lock': {'key': locks['new_key']['id'], 'pick': {'ability': 'dex', 'difficulty': 'hard'}},
        },
        {'entry_id': locks['padlock']['id'], 'lock': {'key': locks['padlock_key']['id']}},
    ]


async def start(client: AsyncClient, me: dict, friend: dict, locks: dict) -> dict:
    """자물쇠 물건을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, locks, **route_doors.the_map(locks), items=the_items(locks))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def replace(place: dict, item: dict) -> dict:
    return {'kind': 'replace', 'place': place['id'], 'item': item['id']}


async def fitted(session: AsyncSession, table: dict) -> list[uuid.UUID | None]:
    """테이블의 문마다 바꿔 단 자물쇠 물건. 판의 길의 순서는 보지 않고 정렬한다(None 은 빼고)."""
    rows = await session.execute(
        text('SELECT lock_item FROM table_route_locks WHERE table_id = :table_id AND lock_item IS NOT NULL'),
        {'table_id': table['id']},
    )
    return sorted(row.lock_item for row in rows)


# --- 시나리오 ---


async def test_lock_items_are_saved_and_published(client: AsyncClient, me: dict, locks: dict):
    scenario = await route_doors.draft(client, me, locks, items=the_items(locks))

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    new_lock, padlock = scenario['items']
    assert new_lock['lock'] == {
        'key': locks['new_key']['id'],
        'pick': {'ability': 'dex', 'difficulty': 'hard', 'tool': None},
    }
    assert padlock['lock'] == {'key': locks['padlock_key']['id'], 'pick': None}
    rules = read_snapshot(response.json()['snapshot']).items
    assert (rules[0].lock.key, rules[0].lock.pick.ability) == (uuid.UUID(locks['new_key']['id']), 'dex')
    assert rules[1].lock.pick is None


@pytest.mark.parametrize('case', ['consumable', 'own-key', 'unknown-field'])
async def test_a_misshaped_lock_item_is_refused(client: AsyncClient, me: dict, locks: dict, case: str):
    lock = {'key': locks['new_key']['id']}
    rules = {
        'consumable': {'kind': 'consumable', 'lock': lock},
        'own-key': {'lock': {'key': locks['new_lock']['id']}},
        'unknown-field': {'lock': {**lock, 'noise': 1}},
    }
    body = {'title': '성의 모험', 'items': [{'entry_id': locks['new_lock']['id'], **rules[case]}]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('pick-ability', 'item_lock_invalid'),
        ('pick-difficulty', 'item_lock_invalid'),
        ('key-not-item', 'item_not_item'),
        ('tool-not-item', 'item_not_item'),
        ('key-of-a-route', 'route_key_repeated'),
        ('key-of-another-item', 'route_key_repeated'),
    ],
)
async def test_a_lock_item_must_fit_the_rules(client: AsyncClient, me: dict, locks: dict, case: str, problem: str):
    key = locks['new_key']['id']
    lock_of = {
        'pick-ability': {'key': key, 'pick': {'ability': 'luck'}},
        'pick-difficulty': {'key': key, 'pick': {'ability': 'dex', 'difficulty': 'impossible'}},
        'key-not-item': {'key': locks['hut']['id']},
        'tool-not-item': {'key': key, 'pick': {'ability': 'dex', 'tool': locks['hut']['id']}},
        'key-of-a-route': {'key': locks['tower_key']['id']},
        'key-of-another-item': {'key': locks['padlock_key']['id']},
    }
    items = [{'entry_id': locks['new_lock']['id'], 'lock': lock_of[case]}, the_items(locks)[1]]
    scenario = await route_doors.draft(client, me, locks, items=items)

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


@pytest.mark.parametrize('case', ['repeated-key', 'key-not-item', 'tool-not-item'])
async def test_the_snapshot_refuses_a_lock_item_that_does_not_fit(
    client: AsyncClient, me: dict, locks: dict, case: str
):
    scenario = await route_doors.draft(client, me, locks, items=the_items(locks))
    document = (await route_doors.publish(client, me, scenario)).json()['snapshot']
    new_lock, padlock = document['items']
    locks_of = {
        'repeated-key': {**new_lock['lock'], 'key': locks['tower_key']['id']},
        'key-not-item': {**new_lock['lock'], 'key': locks['hut']['id']},
        'tool-not-item': {**new_lock['lock'], 'pick': {'ability': 'dex', 'tool': locks['hut']['id']}},
    }
    wrong = {**new_lock, 'lock': locks_of[case]}

    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'items': [wrong, padlock]})
    Snapshot.model_validate(document)


def test_an_old_snapshot_reads_as_no_lock_items():
    document = {'format': 55, 'items': [{'entry_id': 'a', 'kind': 'gear'}]}

    upgraded = upgrade_from_55(document)

    assert upgraded['format'] == 56
    assert upgraded['items'] == [{'entry_id': 'a', 'kind': 'gear', 'lock': None}]
    assert 'lock' not in document['items'][0]
    assert UPGRADES[55] is upgrade_from_55
    assert upgrade_from_55({'format': 55})['items'] == []


# --- 바꾸기 ---


async def test_a_new_lock_is_fitted_open_and_the_lock_item_is_spent(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])

    await play(client, me, friend, table, narrated, mine=replace(locks['hut'], locks['new_lock']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['act'], outcome['device'], outcome['done'], outcome['reason']) == ('replace', None, True, None)
    assert outcome['check'] is None
    seen = await read_table(client, me, table)
    assert ('새 자물쇠', 1) not in held(seen, ME)
    # 판의 물건 목록은 자물쇠 물건인지만 알린다. 열쇠는 싣지 않는다
    catalog = {item['name']: item for item in seen['items']}
    assert (catalog['새 자물쇠']['lock'], catalog['새 열쇠']['lock']) == (True, False)
    assert 'key' not in catalog['새 자물쇠']
    hut = route_out(seen, locks['gate'], locks['hut'])
    # 열린 채다. 따기는 새 자물쇠의 판정이다(어려움)
    assert (hut['locked'], hut['pick']) == (False, {'ability': 'dex', 'difficulty': 'hard'})
    assert await fitted(session, table) == [uuid.UUID(locks['new_lock']['id'])]
    (changed,) = await events_of(client, me, table, 'door_changed')
    assert (changed['payload']['act'], changed['payload']['device']) == ('replace', None)
    assert await events_of(client, me, table, 'check_rolled') == []


async def test_only_the_new_key_works_after_the_lock_is_replaced(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    await give(session, table, ME, locks['new_key'])
    await give(session, table, FRIEND, locks['hut_key'])

    await play(client, me, friend, table, narrated, mine=replace(locks['hut'], locks['new_lock']))
    await play(client, me, friend, table, narrated, mine=route_doors.door('lock', locks['hut'], 'lock'))
    await play(client, me, friend, table, narrated, theirs=route_doors.door('unlock', locks['hut'], 'lock'))
    await play(client, me, friend, table, narrated, theirs=going(locks['hut']))

    locked = await door_outcome(client, me, table, 2)
    unlocked = (await outcome_of(client, me, table, 3, FRIEND))['door']
    # 새 열쇠로 잠갔고, 옛 열쇠로는 열지 못했다. 옛 열쇠로는 지나가지도 못한다
    assert locked['done'] is True
    assert (unlocked['done'], unlocked['reason']) == (False, 'no_key')
    blocked = (await outcome_of(client, me, table, 4, FRIEND))['move']
    assert (blocked['moved'], blocked['reason']) == (False, 'locked')
    assert place_of(await read_table(client, me, table), FRIEND) == locks['gate']['id']


async def test_the_new_key_opens_the_way(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    await give(session, table, ME, locks['new_key'])

    await play(client, me, friend, table, narrated, mine=replace(locks['hut'], locks['new_lock']))
    await play(client, me, friend, table, narrated, mine=route_doors.door('lock', locks['hut'], 'lock'))
    await play(client, me, friend, table, narrated, mine=going(locks['hut']))

    moved = (await outcome_of(client, me, table, 3, ME))['move']
    assert (moved['moved'], moved['unlocked']) == (True, True)


async def test_the_new_lock_is_picked_with_its_own_roll(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    await give(session, table, ME, locks['new_key'])
    load_dice(app, [20])

    await play(client, me, friend, table, narrated, mine=replace(locks['hut'], locks['new_lock']))
    await play(client, me, friend, table, narrated, mine=route_doors.door('lock', locks['hut'], 'lock'))
    await take(session, table, ME, locks['new_key'])
    # 판의 오두막 자물쇠는 따지 못하지만, 새 자물쇠는 락픽 없이 민첩·어려움(20)으로 딴다
    await play(client, me, friend, table, narrated, mine=route_doors.door('pick', locks['hut']))

    picked = await door_outcome(client, me, table, 3)
    assert (picked['done'], picked['check']['ability'], picked['check']['target']) == (True, 'dex', 20)


async def test_a_lock_without_a_pick_cannot_be_picked_once_fitted(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['padlock'])
    await give(session, table, ME, locks['tower_key'])
    await give(session, table, ME, locks['lockpick'])

    await play(client, me, friend, table, narrated, mine=route_doors.door('unlock', locks['square']))
    await play(client, me, friend, table, narrated, mine=replace(locks['square'], locks['padlock']))

    seen = await read_table(client, me, table)
    assert route_out(seen, locks['gate'], locks['square'])['pick'] is None
    response = await declare(client, me, table, route_doors.door('pick', locks['square']))
    assert (response.status_code, response.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_pickable')


async def test_a_pick_finds_no_pick_when_the_lock_was_replaced_before_its_turn(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, FRIEND, locks['lockpick'])
    await declare(client, friend, table, route_doors.door('pick', locks['square']))
    # 받은 뒤 앞 차례에 따지 못하는 자물쇠로 바꿔 달고 잠근 것과 같다
    await session.execute(
        text('UPDATE table_route_locks SET lock_item = :item WHERE table_id = :table_id AND to_place = :square'),
        {'item': locks['padlock']['id'], 'table_id': table['id'], 'square': locks['square']['id']},
    )
    await session.commit()
    await declare(client, me, table, None)
    await narrated()

    theirs = (await outcome_of(client, me, table, 1, FRIEND))['door']
    assert (theirs['done'], theirs['reason'], theirs['check']) == (False, 'no_pick', None)
    assert route_out(await read_table(client, me, table), locks['gate'], locks['square'])['locked'] is True


@pytest.mark.parametrize(('case', 'reason'), [('broken', 'broken'), ('locked', 'locked'), ('gone', 'no_item')])
async def test_a_lock_is_not_replaced_when_the_door_is_not_ready(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated, case: str, reason: str
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    if case == 'broken':
        await break_door(session, table, locks['gate'], locks['hut'])
    place = locks['square'] if case == 'locked' else locks['hut']

    await declare(client, me, table, replace(place, locks['new_lock']))
    if case == 'gone':
        await take(session, table, ME, locks['new_lock'])
    await declare(client, friend, table, None)
    await narrated()

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['reason'], outcome['check']) == (False, reason, None)
    assert await fitted(session, table) == []
    assert await events_of(client, me, table, 'door_changed') == []
    if case != 'gone':
        assert ('새 자물쇠', 1) in held(await read_table(client, me, table), ME)


async def test_a_lock_item_is_fitted_only_once_at_a_table(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    await give(session, table, FRIEND, locks['new_lock'])

    await play(
        client,
        me,
        friend,
        table,
        narrated,
        mine=replace(locks['hut'], locks['new_lock']),
        theirs=replace(locks['hut'], locks['new_lock']),
    )

    mine = await door_outcome(client, me, table)
    theirs = (await outcome_of(client, me, table, 1, FRIEND))['door']
    assert {(mine['done'], mine['reason']), (theirs['done'], theirs['reason'])} == {(True, None), (False, 'used')}
    assert await fitted(session, table) == [uuid.UUID(locks['new_lock']['id'])]


@pytest.mark.parametrize(
    ('case', 'status_code', 'body'),
    [
        ('no-lock-on-the-map', status.HTTP_409_CONFLICT, {'reason': 'not_replaceable'}),
        (
            'not-a-lock-item',
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {'detail': 'action.item 가 이 테이블의 규칙에 없습니다.'},
        ),
        ('not-held', status.HTTP_409_CONFLICT, {'reason': 'item_not_held'}),
    ],
)
async def test_a_replace_is_refused_when_declared(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, case: str, status_code, body
):
    table = await start(client, me, friend, locks)
    await give(session, table, ME, locks['new_lock'])
    await give(session, table, ME, locks['lockpick'])
    action = {
        'no-lock-on-the-map': replace(locks['forest'], locks['new_lock']),
        'not-a-lock-item': replace(locks['hut'], locks['lockpick']),
        'not-held': replace(locks['hut'], locks['padlock']),
    }[case]

    response = await declare(client, me, table, action)

    assert response.status_code == status_code
    assert {key: response.json()[key] for key in body} == body


async def test_a_lock_can_be_replaced_from_either_end(
    client: AsyncClient, me: dict, friend: dict, locks: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, locks)
    await put_at(session, table, ME, locks['hut'])
    await give(session, table, ME, locks['new_lock'])

    await play(client, me, friend, table, narrated, mine=replace(locks['gate'], locks['new_lock']))

    assert (await door_outcome(client, me, table))['done'] is True


# --- 서술과 기록 ---


def test_the_replace_lines():
    fitted_line = DoorNote(act='replace', other_end='오두막', done=True)

    def failed(reason: str) -> str:
        return describe_door(DoorNote(act='replace', other_end='오두막', done=False, reason=reason))

    assert describe_door(fitted_line) == '(문: 오두막 쪽 문. 자물쇠를 새것으로 바꿔 달았다)'
    assert failed('broken') == '(문: 오두막 쪽 문을 새 자물쇠로 바꾸려 했다. 부서진 문이라 먼저 고쳐야 했다)'
    assert failed('locked').endswith('자물쇠가 잠겨 있어 떼지 못했다)')
    assert failed('no_item').endswith('달 자물쇠가 없었다)')
    assert failed('used').endswith('이미 단 적이 있는 자물쇠였다)')
    no_pick = DoorNote(act='pick', other_end='오두막', done=False, reason='no_pick')
    assert describe_door(no_pick).endswith('따지 못하는 자물쇠였다)')
    # 잠그기의 같은 까닭은 그대로다
    assert describe_door(DoorNote(act='lock', other_end='오두막', done=False, reason='broken')).endswith(
        '부서진 문이라 잠기지 않았다)'
    )


def test_the_map_note_says_a_lock_is_replaced_only_by_the_action():
    assert '자물쇠를 바꾸지 말고' in prompt.MAP_NOTE
    assert prompt.PROMPT_VERSION == 'narration-63'


def test_the_transcript_says_the_lock_was_replaced():
    payload = {**SAMPLES['door_changed'], 'act': 'replace', 'device': None}

    assert render_event(event('door_changed', payload), Labels()) == (
        '- 문: 드워프 기사 · 수로 입구 ↔ 깊은 수로 문 자물쇠 바꿈\n'
    )
