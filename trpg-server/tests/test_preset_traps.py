# trpg-server/tests/test_preset_traps.py

"""
미리 놓인 덫과 업혀 들어간 사람(#806 ②-a)을 검증한다.

판과 픽스처는 tests/test_traps.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 시작은 성문. 성문-광장은 열린 큰길이다.
올가미는 덫이다. 피하기는 민첩 보통(15), 해제는 민첩 어려움(20), 효과는 가벼운 피해(1d4). 능력은 모두 10(보정 0)이다.
앉은 순서(기사, 약사)로 판정한다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 미리 놓인 덫(traps: 장소, 덫 물건, 처음부터 아는가)을 저장하고 판에 굳힌다. 맵 밖이면 trap_off_map,
    덫이 아닌 물건이면 trap_not_trap, 붙인 로어북에 없는 물건이면 item_entry_missing 이다. 판이 거부한다.
  - 시작: 덫마다 테이블의 덫이 놓은 사람 없이 놓인다. 숨긴 덫은 들어온 캐릭터가 밟고, 아는 덫은 맵에 보이고 밟지 않는다.
  - 업기: 업은 사람이 못 피하면 업힌 사람에게도 효과가 든다. 피했으면 둘 다 멀쩡하다. 이벤트와 서술에도 적힌다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot
from app.rounds.move_lines import describe_travel
from app.rounds.narration_request import to_trap
from app.rounds.narrator import TrapNote, TravelNote
from app.rounds.router import visible_outcome
from tests import test_traps as trap_tests
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import declare, going, outcome_of, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, post, read_table, table_url
from tests.test_table_map import open_duo
from tests.test_traps import CAUGHT, DODGE, hp_of, item_rules, the_map, traps_of
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = trap_tests.me
friend = trap_tests.friend
lore = trap_tests.lore
snares = trap_tests.snares


def placed(world: dict, place: str, item: str = 'snare', known: bool = False) -> dict:
    return {'place_id': world[place]['id'], 'entry_id': world[item]['id'], 'known': known}


async def draft(client: AsyncClient, me: dict, world: dict, traps: list[dict]) -> dict:
    """미리 놓인 덫을 적은 시나리오. 게시하지 않았다."""
    rulebook = await post(client, trap_tests.map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': trap_tests.map_tables.SHEET,
        'lorebook_ids': [world['lorebook']['id']],
        'items': item_rules(world),
        'traps': traps,
        **the_map(world),
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, friend: dict, world: dict, traps: list[dict]) -> dict:
    """미리 놓인 덫을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, world, items=item_rules(world), traps=traps, **the_map(world))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def downed(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람을 쓰러진 채 안정된 상태로 둔다(죽음의 굴림을 굴리지 않는다). 테스트의 준비다."""
    query = 'UPDATE table_sheets SET hp = 0, death_successes = 3 WHERE user_id = :user_id'
    await session.execute(text(query), {'user_id': user_id})
    await session.commit()


def carrying(world: dict, place: str, user_id: uuid.UUID) -> dict:
    return {'kind': 'move', 'place': world[place]['id'], 'carry': str(user_id)}


async def carry_alone(client: AsyncClient, me: dict, table: dict, narrated, action: dict) -> None:
    """쓰러진 사람은 선언하지 않는다. 나 혼자 선언해 라운드를 닫고 서술을 기다린다."""
    declared = await declare(client, me, table, action)
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()


def known_at(table: dict, place: dict) -> list[str]:
    found = next(spot for spot in table['map']['places'] if spot['entry_id'] == place['id'])
    return [trap['name'] for trap in found['traps']]


# --- 시나리오 ---


async def test_preset_traps_are_saved_and_published(client: AsyncClient, me: dict, snares: dict):
    traps = [placed(snares, 'square'), placed(snares, 'gate', known=True)]
    scenario = await draft(client, me, snares, traps)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['traps'] == traps
    assert response.json()['snapshot']['traps'] == traps


@pytest.mark.parametrize(
    ('case', 'problem'),
    [('off-map', 'trap_off_map'), ('not-trap', 'trap_not_trap'), ('missing', 'item_entry_missing')],
)
async def test_a_preset_trap_must_fit(client: AsyncClient, me: dict, snares: dict, case: str, problem: str):
    world = {**snares, 'nowhere': {'id': str(uuid.uuid4())}}
    trap = {
        'off-map': placed(world, 'tower'),
        'not-trap': placed(world, 'gate', item='potion'),
        'missing': placed(world, 'gate', item='nowhere'),
    }[case]
    scenario = await draft(client, me, world, [trap])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert problem in response.json()['problems']


async def test_a_misshaped_preset_trap_is_refused(client: AsyncClient, me: dict, snares: dict):
    body = {'title': '성의 모험', 'traps': [{**placed(snares, 'gate'), 'armed': True}]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_snapshot_refuses_a_wrong_preset_trap(client: AsyncClient, me: dict, snares: dict):
    document = (await publish(client, me, await draft(client, me, snares, [placed(snares, 'gate')]))).json()['snapshot']
    not_trap = [{**document['traps'][0], 'entry_id': snares['potion']['id']}]
    off_place = [{**document['traps'][0], 'place_id': str(uuid.uuid4())}]

    for traps in (not_trap, off_place):
        with pytest.raises(ValidationError):
            Snapshot.model_validate({**document, 'traps': traps})
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'start_place': None, 'routes': []})
    Snapshot.model_validate(document)


# --- 시작 ---


async def test_a_hidden_preset_trap_springs_on_who_comes(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, [placed(snares, 'square')])
    assert await traps_of(session) == [(None, None)]
    assert known_at(table, snares['square']) == []
    load_dice(app, [CAUGHT, 2])

    await play(client, me, friend, table, narrated, mine=going(snares['square']))

    (sprung,) = (await outcome_of(client, me, table, 1, ME))['move']['traps']
    assert (sprung['set_by'], sprung['avoided'], sprung['effect']['after'], sprung['carried']) == (None, False, 8, None)
    assert await traps_of(session) == [(None, 'sprung')]


async def test_a_known_preset_trap_is_shown_and_stepped_around(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, [placed(snares, 'square', known=True)])
    await play(client, me, friend, table, narrated, mine=going(snares['square']))
    load_dice(app, [])

    seen = await read_table(client, friend, table)

    assert known_at(seen, snares['square']) == ['올가미']
    assert (await outcome_of(client, me, table, 1, ME))['move']['traps'] == []
    found_at = await session.scalar(text('SELECT found_at FROM table_traps'))
    assert found_at is not None


# --- 업기 ---


async def test_the_carried_one_is_caught_with_the_carrier(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, [placed(snares, 'square')])
    await downed(session, FRIEND)
    # 업은 사람의 피하는 판정 3(실패), 업은 사람의 피해 2, 업힌 사람의 피해 1
    load_dice(app, [CAUGHT, 2, 1])

    await carry_alone(client, me, table, narrated, carrying(snares, 'square', FRIEND))

    (sprung,) = (await outcome_of(client, me, table, 1, ME))['move']['traps']
    carried = sprung['carried']
    assert (carried['user_id'], carried['character_name']) == (str(FRIEND), '약사')
    assert (carried['effect']['kind'], carried['effect']['amount']) == ('damage', 1)
    assert hp_of(await read_table(client, me, table), ME) == 8
    (fired,) = await events_of(client, me, table, 'trap_sprung')
    assert fired['payload']['carried'] == {'user_id': str(FRIEND), 'character_name': '약사'}
    changed = await events_of(client, me, table, 'hp_changed')
    assert {event['payload']['character_name'] for event in changed} == {'기사', '약사'}
    assert all(event['caused_by_sequence'] == fired['sequence'] for event in changed)


async def test_a_dodge_spares_the_carried_one(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, [placed(snares, 'square')])
    await downed(session, FRIEND)
    load_dice(app, [DODGE])

    await carry_alone(client, me, table, narrated, carrying(snares, 'square', FRIEND))

    (sprung,) = (await outcome_of(client, me, table, 1, ME))['move']['traps']
    assert sprung['carried'] == {
        'user_id': str(FRIEND),
        'character_name': '약사',
        'effect': None,
        'injured': [],
        'resources': [],
    }
    assert await events_of(client, me, table, 'hp_changed') == []


async def test_the_narrator_hears_the_carried_one_caught(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    recording = RecordingNarrator()
    app.state.narrator = recording
    table = await start(client, me, friend, snares, [placed(snares, 'square')])
    await downed(session, FRIEND)
    load_dice(app, [CAUGHT, 2, 1])

    await carry_alone(client, me, table, narrated, carrying(snares, 'square', FRIEND))

    (request,) = recording.requests
    knight = next(move for move in request.moves if move.character_name == '기사')
    assert knight.travel.traps == [TrapNote(name='올가미', check='민첩', avoided=False, carried='약사')]


def test_the_narration_line_of_a_carried_catch():
    caught = TrapNote(name='올가미', check='민첩', avoided=False, carried='약사')
    note = TravelNote('성문', '광장', True, carried='약사', traps=[caught])

    assert (
        describe_travel(note)
        == '(간 곳: 성문 → 광장, 약사을(를) 업고)(덫: 올가미. 민첩 판정에 실패해 걸렸다. 업힌 약사도 걸렸다)'
    )
    carried = {'user_id': 'u', 'character_name': '약사'}
    assert (
        to_trap({'name': '올가미', 'avoid': {'ability': 'dex'}, 'avoided': True, 'carried': carried}, None).carried
        is None
    )
    assert (
        to_trap({'name': '올가미', 'avoid': {'ability': 'dex'}, 'avoided': False, 'carried': carried}, None).carried
        == '약사'
    )


def test_a_hidden_shift_of_the_carried_one_is_left_out():
    shift = {'resource': 'mana', 'before': 3, 'after': 1, 'max': 7, 'user_id': str(FRIEND), 'visibility': 'owner'}
    trap = {'name': '올가미', 'resources': [], 'carried': {'character_name': '약사', 'resources': [shift]}}
    outcome = {'move': {'moved': True, 'traps': [trap]}}

    assert visible_outcome(outcome, FRIEND)['move']['traps'][0]['carried']['resources'] == [shift]
    assert visible_outcome(outcome, ME)['move']['traps'][0]['carried']['resources'] == []


def test_only_a_carried_one_is_caught():
    from types import SimpleNamespace

    from app.rounds import trap_actions

    judging = SimpleNamespace(table=SimpleNamespace(members=[]))

    assert trap_actions.carried_member(judging, None) is None
    assert trap_actions.carried_member(judging, {'user_id': str(FRIEND), 'carried': False}) is None
