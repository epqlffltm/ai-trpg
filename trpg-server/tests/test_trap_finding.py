# trpg-server/tests/test_trap_finding.py

"""
덫 찾기와 해제(#806 ①-b)를 검증한다.

판과 픽스처는 tests/test_traps.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 시작은 성문. 성문-광장은 열린 큰길이다.
올가미는 덫이다. 피하기는 민첩 보통(15), 해제는 민첩 어려움(20), 효과는 가벼운 피해(1d4).
찾기 판정은 비워 피하기로 찾는다.
시트의 능력은 모두 10(보정 0)이다. 앉은 순서(기사, 약사)로 판정한다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 덫의 찾기 판정(find)을 저장하고 판에 굳힌다. 룰북에 없으면 item_trap_invalid 다.
  - 찾기: 찾기 행동이 그 장소의 숨긴 덫마다 찾는 판정을 굴린다. 찾으면 결과와 place_searched 에 적히고,
    테이블 모두가 맵에서 본다. 못 찾은 것은 어디에도 없다. 덫에 찾기 판정이 있으면 그것으로 굴린다.
  - 아는 덫: 캐릭터가 들어와도 터지지 않는다.
  - 해제: 지금 장소의 찾아낸 덫만 받는다. 성공하면 거둬 갖고(가득이면 그 자리에 보이게 둔다), 실패하면 그대로,
    목표보다 5 이상 모자라면 터진다. 앞사람이 거둔 덫은 굴리지 않는다(gone). trap_disarmed 이벤트가 남는다.
  - 보이기, 서술, 되돌리기.
"""

import importlib.util
import pathlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds.move_lines import describe_disarm, describe_move, describe_search
from app.rounds.narration_request import to_disarm
from app.rounds.narrator import DisarmNote, SearchNote
from app.rounds.router import visible_outcome
from tests import test_traps as trap_tests
from tests.test_character_death import load_dice
from tests.test_map_actions import declare, going, outcome_of, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, give, held, read_table
from tests.test_traps import CAUGHT, DODGE, TRAP, draft, hp_of, setting, start, traps_of
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

MIGRATION = pathlib.Path(__file__).parent.parent / 'migrations/versions/20261117_e8a0c2d4f6b9_trap_finding.py'
SEARCHING = {'kind': 'search'}
# 해제 판정(민첩 어려움, 목표 20)의 눈. 20 이면 거둔다. 16 은 4 모자라 그대로, 15 는 5 모자라 터진다
SUCCESS, NEAR, FUMBLE = 20, 16, 15

me = trap_tests.me
friend = trap_tests.friend
lore = trap_tests.lore
snares = trap_tests.snares


def disarming(trap_id: str) -> dict:
    return {'kind': 'disarm', 'trap': trap_id}


def known_at(table: dict, place: dict) -> list[dict]:
    """응답의 맵에서 그 장소의 찾아낸 덫들."""
    found = next(spot for spot in table['map']['places'] if spot['entry_id'] == place['id'])
    return found['traps']


def items_at(table: dict, place: dict) -> list[tuple[str, int]]:
    found = next(spot for spot in table['map']['places'] if spot['entry_id'] == place['id'])
    return [(item['name'], item['count']) for item in found['items']]


async def found_trap(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
) -> tuple[dict, str]:
    """기사가 성문에 올가미를 놓고(1 라운드), 찾아낸다(2 라운드). 테이블과 덫의 id 를 돌려준다. 약사는 성문에 있다."""
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares))
    load_dice(app, [DODGE])
    await play(client, me, friend, table, narrated, mine=SEARCHING)
    (trap,) = (await outcome_of(client, me, table, 2, ME))['search']['traps']
    return table, trap['trap_id']


# --- 시나리오 ---


async def test_a_find_check_is_saved_and_checked(client: AsyncClient, me: dict, snares: dict):
    scenario = await draft(client, me, snares, {**TRAP, 'find': {'ability': 'wis', 'difficulty': 'hard'}})
    assert scenario['items'][0]['trap']['find'] == {'ability': 'wis', 'difficulty': 'hard'}
    wrong = await draft(client, me, snares, {**TRAP, 'find': {'ability': 'luck'}})

    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    refused = await client.post(f'{SCENARIOS_URL}/{wrong["id"]}/versions', json={}, headers=me)

    assert published.status_code == status.HTTP_201_CREATED, published.text
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == ['item_trap_invalid']


# --- 찾기 ---


async def test_searching_finds_a_trap_for_everyone(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)

    search = (await outcome_of(client, me, table, 2, ME))['search']
    assert search['traps'] == [{'trap_id': trap_id, 'entry_id': snares['snare']['id'], 'name': '올가미'}]
    known = [{'trap_id': trap_id, 'entry_id': snares['snare']['id'], 'name': '올가미'}]
    assert known_at(await read_table(client, friend, table), snares['gate']) == known
    (searched,) = await events_of(client, friend, table, 'place_searched')
    assert searched['payload']['traps'] == known
    found_at = await session.scalar(text('SELECT found_at FROM table_traps'))
    assert found_at is not None


async def test_a_found_trap_is_not_found_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, _ = await found_trap(client, app, me, friend, snares, session, narrated)
    # 아는 덫은 다시 굴리지 않는다. 주사위를 꽂지 않았다
    load_dice(app, [])

    await play(client, me, friend, table, narrated, theirs=SEARCHING)

    assert (await outcome_of(client, me, table, 3, FRIEND))['search']['traps'] == []


async def test_a_missed_trap_stays_hidden(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares))
    load_dice(app, [CAUGHT])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert (await outcome_of(client, me, table, 2, ME))['search']['traps'] == []
    assert known_at(await read_table(client, me, table), snares['gate']) == []
    assert await session.scalar(text('SELECT found_at FROM table_traps')) is None


async def test_a_trap_with_its_own_find_check_uses_it(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    # 피하기(보통 15)로는 찾는 눈이지만 찾기 판정(지혜 어려움 20)에는 모자란다
    table = await start(client, me, friend, snares, session, {**TRAP, 'find': {'ability': 'wis', 'difficulty': 'hard'}})
    await play(client, me, friend, table, narrated, mine=setting(snares))
    load_dice(app, [DODGE])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    assert (await outcome_of(client, me, table, 2, ME))['search']['traps'] == []


async def test_a_known_trap_is_stepped_around(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, _ = await found_trap(client, app, me, friend, snares, session, narrated)
    await play(client, me, friend, table, narrated, mine=going(snares['square']))
    load_dice(app, [])

    await play(client, me, friend, table, narrated, mine=going(snares['gate']))

    assert (await outcome_of(client, me, table, 4, ME))['move']['traps'] == []
    assert hp_of(await read_table(client, me, table), ME) == 10
    assert await traps_of(session) == [(ME, None)]


# --- 해제 ---


@pytest.mark.parametrize('which', ['unknown', 'hidden', 'elsewhere'])
async def test_only_a_known_trap_here_is_accepted(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated, which
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['square']))
    trap_id = str(await session.scalar(text('SELECT id FROM table_traps')))
    if which == 'elsewhere':
        load_dice(app, [DODGE])
        await play(client, me, friend, table, narrated, mine=SEARCHING)
    target = str(uuid.uuid4()) if which == 'unknown' else trap_id
    headers = friend if which == 'elsewhere' else me

    response = await declare(client, headers, table, disarming(target))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_disarmed_trap_is_kept(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    load_dice(app, [SUCCESS])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id))

    disarm = (await outcome_of(client, me, table, 3, ME))['disarm']
    assert disarm == {
        'user_id': str(ME),
        'character_name': '기사',
        'place': {'entry_id': snares['gate']['id'], 'name': '성문'},
        'trap_id': trap_id,
        'entry_id': snares['snare']['id'],
        'name': '올가미',
        'done': True,
        'reason': None,
        'check': {
            'ability': 'dex',
            'difficulty': 'hard',
            'roll': SUCCESS,
            'modifier': 0,
            'total': SUCCESS,
            'target': 20,
            'success': True,
            'hindrance': None,
        },
        'sprung': False,
        'effect': None,
        'injured': [],
        'resources': [],
        'kept': 1,
    }
    seen = await read_table(client, me, table)
    assert held(seen, ME) == [('올가미', 2)]
    assert known_at(seen, snares['gate']) == []
    assert await traps_of(session) == [(ME, 'disarmed')]
    (disarmed,) = await events_of(client, friend, table, 'trap_disarmed')
    acted = next(
        event for event in await events_of(client, me, table, 'player_action') if event['payload']['round'] == 3
    )
    assert disarmed['caused_by_sequence'] == acted['sequence']
    assert disarmed['payload'] == {
        'round': 3,
        'character_name': '기사',
        'place': disarm['place'],
        'trap_id': trap_id,
        'entry_id': snares['snare']['id'],
        'name': '올가미',
        'done': True,
        'reason': None,
        'check': disarm['check'],
        'sprung': False,
        'kept': 1,
    }


async def test_a_near_miss_leaves_the_trap(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    load_dice(app, [NEAR])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id))

    disarm = (await outcome_of(client, me, table, 3, ME))['disarm']
    assert (disarm['done'], disarm['sprung'], disarm['effect'], disarm['kept']) == (False, False, None, 0)
    assert await traps_of(session) == [(ME, None)]
    assert len(known_at(await read_table(client, me, table), snares['gate'])) == 1
    assert await events_of(client, me, table, 'hp_changed') == []


async def test_a_fumble_springs_the_trap(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    # 해제 판정의 눈 15(5 모자람), 피해의 눈 2. 피하는 판정은 굴리지 않는다
    load_dice(app, [FUMBLE, 2])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id))

    disarm = (await outcome_of(client, me, table, 3, ME))['disarm']
    assert (disarm['done'], disarm['sprung'], disarm['kept']) == (False, True, 0)
    assert (disarm['effect']['amount'], disarm['effect']['after']) == (2, 8)
    assert hp_of(await read_table(client, me, table), ME) == 8
    assert await traps_of(session) == [(ME, 'sprung')]
    (disarmed,) = await events_of(client, me, table, 'trap_disarmed')
    (changed,) = await events_of(client, me, table, 'hp_changed')
    assert changed['caused_by_sequence'] == disarmed['sequence']


async def test_a_trap_taken_by_the_one_before_is_gone(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    load_dice(app, [SUCCESS])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id), theirs=disarming(trap_id))

    disarm = (await outcome_of(client, me, table, 3, FRIEND))['disarm']
    assert (disarm['done'], disarm['reason'], disarm['check'], disarm['name']) == (False, 'gone', None, '올가미')
    (_, late) = await events_of(client, me, table, 'trap_disarmed')
    assert (late['payload']['character_name'], late['payload']['reason']) == ('약사', 'gone')


async def test_a_full_hand_leaves_the_trap_lying(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    await give(session, table, ME, snares['snare'], 98)
    load_dice(app, [SUCCESS])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id))

    assert (await outcome_of(client, me, table, 3, ME))['disarm']['kept'] == 0
    seen = await read_table(client, me, table)
    assert held(seen, ME) == [('올가미', 99)]
    assert items_at(seen, snares['gate']) == [('올가미', 1)]


# --- 보이기와 서술과 되돌리기 ---


def test_a_hidden_disarm_shift_is_left_out_for_others():
    shift = {'resource': 'mana', 'before': 3, 'after': 1, 'max': 7, 'user_id': str(ME), 'visibility': 'owner'}
    outcome = {'disarm': {'name': '올가미', 'resources': [shift]}}

    assert visible_outcome(outcome, ME)['disarm']['resources'] == [shift]
    assert visible_outcome(outcome, FRIEND)['disarm']['resources'] == []


def test_the_narration_lines_of_finding_and_disarming():
    assert describe_search(SearchNote(place='성문', traps=['올가미'])) == '(찾기: 덫을 찾아냈다. 올가미)'
    assert describe_disarm(DisarmNote(name='올가미', check='민첩', done=True)) == (
        '(해제: 올가미. 민첩 판정에 성공해 거둬 챙겼다)'
    )
    assert describe_disarm(DisarmNote(name='올가미', check='민첩', done=False)) == (
        '(해제: 올가미. 민첩 판정에 실패했다. 덫은 그대로다)'
    )
    assert describe_disarm(DisarmNote(name='올가미', check='민첩', done=False, sprung=True)) == (
        '(해제: 올가미. 민첩 판정에 크게 실패해 덫이 터졌다)'
    )
    assert (
        describe_disarm(DisarmNote(name='올가미', check=None, done=False, reason='gone')) == '(해제: 덫이 이미 없었다)'
    )
    assert describe_disarm(DisarmNote(name=None, check=None, done=False, reason='elsewhere')) == (
        '(해제: 덫이 있는 곳에 없었다)'
    )


async def test_the_narrator_hears_the_finding_and_the_disarming(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    recording = RecordingNarrator()
    app.state.narrator = recording
    table, trap_id = await found_trap(client, app, me, friend, snares, session, narrated)
    load_dice(app, [SUCCESS])

    await play(client, me, friend, table, narrated, mine=disarming(trap_id))

    _, searched, disarmed = recording.requests
    finder = next(move for move in searched.moves if move.character_name == '기사')
    assert finder.search.traps == ['올가미']
    assert '(찾기: 덫을 찾아냈다. 올가미)' in describe_move(finder)
    remover = next(move for move in disarmed.moves if move.character_name == '기사')
    assert remover.disarm == DisarmNote(name='올가미', check='민첩', done=True)
    assert '(해제: 올가미. 민첩 판정에 성공해 거둬 챙겼다)' in describe_move(remover)


def test_an_unrolled_disarm_reads_without_a_check():
    disarm = {'name': None, 'check': None, 'done': False, 'sprung': False, 'reason': 'gone'}
    declaration = SimpleNamespace(outcome={'disarm': disarm})

    assert to_disarm(declaration) == DisarmNote(name=None, check=None, done=False, reason='gone')


def test_downgrade_strips_the_find_check():
    spec = importlib.util.spec_from_file_location('trap_finding_migration', MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    rules = [
        {'entry_id': 'a', 'trap': {**TRAP, 'find': {'ability': 'wis'}}},
        {'entry_id': 'b', 'kind': 'gear'},
        {'entry_id': 'c', 'trap': None},
    ]

    assert migration.without_find(rules) == [
        {'entry_id': 'a', 'trap': TRAP},
        {'entry_id': 'b', 'kind': 'gear'},
        {'entry_id': 'c', 'trap': None},
    ]
    assert migration.without_find(None) == []
    assert rules[0]['trap']['find'] == {'ability': 'wis'}
