# trpg-server/tests/test_happening_traps.py

"""
판의 사건이 옮긴 캐릭터와 인물이 닿은 곳의 덫을 밟는 것(#806 ②-c, app/rounds/happening_traps.py)을 검증한다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길,
광장→지하실 숨긴 길, 탑은 명소. 여기에 덫 물건(올가미), 사건 항목 둘(함정, 교대), 성문에 선 인물(경비대장)을 더한다.
올가미의 규칙은 tests/test_traps.py 의 것이다. 피하기는 민첩 보통(15), 효과는 가벼운 피해(1d4). 능력은 모두 10 이다.

보는 것.
  - 캐릭터: 사건이 옮긴 곳의 숨긴 덫을 들어간 것처럼 밟는다. 찾아낸 덫은 밟지 않는다.
    밟은 것은 사건의 줄(table_happenings.traps)에 적고, 사건의 이벤트에는 싣지 않는다.
    이벤트는 사건(happening_occurred)에 trap_sprung 이 잇는다.
  - 인물: 사건이 옮긴 곳의 덫을 찾아냈든 아니든 밟는다. 장면 밖(아무도 없는 곳)이어도 밟는다.
    trap_sprung 과 npc_changed 가 사건에 잇는다.
  - 서술: 일행이 본 것만 [일어난 사건]의 줄에 붙는다. 캐릭터는 늘, 인물은 그 장소에 일행이 있을 때만이다.
  - 마이그레이션: 사건의 줄에 덫 칸을 더하고 되돌리면 지운다.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import prompt
from app.rounds.narration_request import describe_happening_trap, is_trap_seen
from app.rounds.narrator import HappeningNote
from tests import test_table_map as map_tables
from tests.sheets import make_sheet
from tests.test_character_death import NO_INJURY, load_dice
from tests.test_map_actions import going, play
from tests.test_table_items import ME, events_of, post, read_table, table_url
from tests.test_table_map import open_duo, place_of, the_map
from tests.test_traps import CAUGHT, DODGE, hp_of, item_rules, traps_of
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore


@pytest.fixture
async def world(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 올가미, 사건 둘(함정, 교대), 인물 하나(경비대장)를 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'

    async def entry(name: str, kind: str, keywords: list[str]) -> dict:
        return await post(client, url, me, name=name, keywords=keywords, content=f'{name}의 설명', kind=kind)

    return {
        **lore,
        'snare': await entry('올가미', 'item', []),
        'pit': await entry('함정', 'event', []),
        'shift': await entry('교대', 'event', []),
        'captain': await entry('알베르트', 'person', ['경비', '경비대장']),
    }


def placed(world: dict, place: str, known: bool = False) -> dict:
    return {'place_id': world[place]['id'], 'entry_id': world['snare']['id'], 'known': known}


def reach_square(world: dict, entry: str, effect: dict) -> dict:
    """광장에 닿으면 일어나는 사건."""
    when = [{'kind': 'reach_place', 'target': world['square']['id']}]
    return {'entry_id': world[entry]['id'], 'when': when, 'effects': [effect]}


def pit(world: dict) -> dict:
    """광장에 닿으면 광장에 선 사람이 숨긴 지하실로 떨어진다."""
    move = {'kind': 'move', 'to_place': world['cellar']['id'], 'from_place': world['square']['id']}
    return reach_square(world, 'pit', move)


def shift(world: dict, to: str) -> dict:
    """광장에 닿으면 경비대장이 그곳으로 간다."""
    return reach_square(
        world, 'shift', {'kind': 'move_npc', 'npc': world['captain']['id'], 'to_place': world[to]['id']}
    )


async def start(
    client: AsyncClient,
    me: dict,
    friend: dict,
    world: dict,
    happening: dict,
    traps: list[dict],
    captain: str = 'gate',
    **fields,
) -> dict:
    """그 사건과 미리 놓인 덫으로 둘이 앉아 시작한 테이블. 경비대장은 captain 장소(기본은 성문)에 있다."""
    scenario = {
        **the_map(world),
        'items': item_rules(world),
        'traps': traps,
        'happenings': [happening],
        'default_npc_sheet': make_sheet(max_hp=6),
        'npc_places': [{'entry_id': world['captain']['id'], 'place_id': world[captain]['id']}],
        **fields,
    }
    table = await open_duo(client, me, friend, world, **scenario)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == 200, started.text
    return started.json()


async def stored_traps(session: AsyncSession) -> list[dict]:
    return await session.scalar(text('SELECT traps FROM table_happenings'))


async def captain_hp(session: AsyncSession) -> int:
    return await session.scalar(text('SELECT hp FROM table_npcs'))


# --- 캐릭터 ---


async def test_the_one_dropped_into_a_hidden_trap_is_caught(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, world, pit(world), [placed(world, 'cellar')])
    # 피하는 판정 3(실패), 피해 2
    load_dice(app, [CAUGHT, 2])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    seen = await read_table(client, friend, table)
    assert (place_of(seen, ME), hp_of(seen, ME)) == (world['cellar']['id'], 8)
    assert await traps_of(session) == [(None, 'sprung')]
    (one,) = await stored_traps(session)
    assert (one['kind'], one['user_id'], one['place']['name'], one['trap']['avoided']) == (
        'pc',
        str(ME),
        '지하실',
        False,
    )
    # 사건의 이벤트에는 싣지 않는다. 덫은 사건에 잇는다
    (occurred,) = await events_of(client, friend, table, 'happening_occurred')
    assert 'traps' not in occurred['payload']
    (fired,) = await events_of(client, friend, table, 'trap_sprung')
    assert fired['caused_by_sequence'] == occurred['sequence']
    assert (fired['payload']['character_name'], fired['payload']['place']['name']) == ('기사', '지하실')
    (request,) = narrator.requests
    assert request.happenings == [HappeningNote(name='함정', moved=['기사 → 지하실'], traps=['기사: 덫 올가미에 걸림'])]


async def test_a_found_trap_is_not_stepped_on_by_the_dropped(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, world, pit(world), [placed(world, 'cellar', known=True)])
    load_dice(app, [])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    assert hp_of(await read_table(client, me, table), ME) == 10
    assert await traps_of(session) == [(None, None)]
    assert await stored_traps(session) == []
    assert await events_of(client, me, table, 'trap_sprung') == []


# --- 인물 ---


async def test_a_person_moved_out_of_sight_steps_on_a_trap_unseen(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, world, shift(world, 'tower'), [placed(world, 'tower')] * 2)
    # 놓인 덫 둘을 차례로 밟는다. 피하는 판정 3(실패), 피해 2 를 두 번
    load_dice(app, [CAUGHT, 2, CAUGHT, 1])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    assert await captain_hp(session) == 3
    assert await traps_of(session) == [(None, 'sprung'), (None, 'sprung')]
    first, second = await stored_traps(session)
    assert (first['kind'], first['entry_id'], first['place']['name']) == ('npc', world['captain']['id'], '탑')
    assert (first['trap']['npc_effect']['after'], second['trap']['npc_effect']['after']) == (4, 3)
    (occurred,) = await events_of(client, me, table, 'happening_occurred')
    fired = await events_of(client, me, table, 'trap_sprung')
    changed = await events_of(client, me, table, 'npc_changed')
    assert [one['caused_by_sequence'] for one in fired] == [occurred['sequence']] * 2
    assert [one['caused_by_sequence'] for one in changed] == [one['sequence'] for one in fired]
    assert [one['payload']['npc_id'] for one in fired] == [world['captain']['id']] * 2
    # 떠나는 것은 성문의 약사가 봤다. 밟은 곳은 아무도 없는 탑이라 서술은 밟은 것을 받지 않는다
    (request,) = narrator.requests
    assert request.happenings == [HappeningNote(name='교대', moved=['경비대장 → 탑'], traps=[])]


async def test_a_person_steps_on_a_found_trap_where_the_party_stands(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, world, shift(world, 'square'), [placed(world, 'square', known=True)])
    # 기사는 찾아낸 덫을 밟지 않는다. 경비대장은 피한다(18)
    load_dice(app, [DODGE])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    assert (hp_of(await read_table(client, me, table), ME), await captain_hp(session)) == (10, 6)
    assert await traps_of(session) == [(None, 'sprung')]
    assert await events_of(client, me, table, 'npc_changed') == []
    (request,) = narrator.requests
    assert request.happenings == [
        HappeningNote(name='교대', moved=['경비대장 → 광장'], traps=['경비대장: 덫 올가미을(를) 피함'])
    ]


async def test_a_person_downed_by_the_trap_drops_to_the_one_standing_there(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    # 경비대장은 HP 1 이고 치유 물약 하나를 반드시 떨군다. 광장에는 기사만 있다
    weak = {
        'entry_id': world['captain']['id'],
        'sheet': make_sheet(max_hp=1),
        'inventory': [{'entry_id': world['potion']['id'], 'count': 1, 'chance': 100}],
    }
    traps = [placed(world, 'square', known=True)]
    table = await start(client, me, friend, world, shift(world, 'square'), traps, npc_sheets=[weak])
    # 피하는 판정 3(실패), 피해 2, 부상 표 1(부상 없음). 반드시 떨어지는 것은 굴리지 않는다
    dice = load_dice(app, [CAUGHT, 2, NO_INJURY])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    (one,) = await stored_traps(session)
    assert one['trap']['npc_effect']['status'] == 'downed'
    assert (one['trap']['drop']['user_id'], one['trap']['drop']['items'][0]['name']) == (str(ME), '치유 물약')
    assert dice.remaining == 0


async def test_a_person_out_of_the_scene_steps_on_it_too(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    # 경비대장은 아무도 없는 탑에 있다가 숨긴 지하실로 간다. 장면에 든 적이 없다
    table = await start(client, me, friend, world, shift(world, 'cellar'), [placed(world, 'cellar')], captain='tower')
    load_dice(app, [CAUGHT, 2])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    assert await captain_hp(session) == 4
    assert await traps_of(session) == [(None, 'sprung')]
    (fired,) = await events_of(client, me, table, 'trap_sprung')
    assert fired['payload']['npc_name'] == '경비대장'


async def test_without_a_trap_nothing_is_stepped_on(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, world, shift(world, 'tower'), [placed(world, 'cellar')])
    load_dice(app, [])

    await play(client, me, friend, table, narrated, mine=going(world['square']))

    assert (await captain_hp(session), await stored_traps(session)) == (6, [])
    assert await traps_of(session) == [(None, None)]


# --- 작은 함수 ---

TOWER = uuid.uuid4()


def stepped(kind: str, avoided: bool, **who) -> dict:
    return {
        'kind': kind,
        **who,
        'place': {'entry_id': str(TOWER), 'name': '탑'},
        'trap': {'name': '올가미', 'avoided': avoided},
    }


def test_a_trapped_character_is_always_seen_and_a_person_only_where_the_party_is():
    character = stepped('pc', False, user_id=str(ME), character_name='기사')
    person = stepped('npc', False, entry_id=str(uuid.uuid4()), name='알베르트')

    assert is_trap_seen(character, frozenset())
    assert not is_trap_seen(person, frozenset({uuid.uuid4()}))
    assert is_trap_seen(person, frozenset({TOWER}))


def test_the_line_of_a_trap_names_who_and_how():
    captain = uuid.uuid4()
    character = stepped('pc', True, user_id=str(ME), character_name='기사')
    person = stepped('npc', False, entry_id=str(captain), name='알베르트')

    assert describe_happening_trap(character, {}) == '기사: 덫 올가미을(를) 피함'
    assert describe_happening_trap(person, {captain: '경비대장'}) == '경비대장: 덫 올가미에 걸림'
    assert describe_happening_trap(person, {}) == '알베르트: 덫 올가미에 걸림'


def test_the_trap_comes_after_the_moves_on_the_happening_line():
    note = HappeningNote('교대', ['경비대장 → 광장'], traps=['경비대장: 덫 올가미에 걸림'])

    assert prompt.happening_lines([note])[2] == '- 교대: 경비대장 → 광장, 경비대장: 덫 올가미에 걸림'
