# trpg-server/tests/test_traps.py

"""
덫(#806 ①-a)을 검증한다. 아이템 규칙의 덫, 덫을 놓는 행동(set_trap), 장소에 들어온 캐릭터가 덫을 터뜨리는 것이다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 시작은 성문.
성문-광장은 열린 큰길이다. 여기에 물건 하나(올가미)를 더하고, 판의 아이템 규칙에서 덫으로 적는다.
  - 피하기: 민첩(난이도는 비워 규칙의 기본인 보통 15). 해제: 민첩 어려움.
  - 효과: 가벼운 피해(1d4).
시트의 민첩은 10(보정 0)이다. 몬스터와 싸우는 인물이 없어 앉은 순서(기사, 약사)로 판정한다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 덫을 저장하고 판에 굳힌다. 잘못 둔 것은 422, 룰북에 없는 것은 409(item_trap_invalid)다.
    테이블의 물건에 덫이 보인다.
  - 놓기: 지닌 덫 하나가 빠지고 그 장소에 놓인다. 결과와 trap_set 이벤트가 남는다.
    덫이 아닌 물건이나 지니지 않은 것은 받지 않는다. 차례가 왔을 때 없으면 놓지 않는다(not_held).
  - 터뜨리기: 놓인 장소에 들어온 캐릭터가 피하는 판정을 굴린다. 실패하면 효과가 들고, 피해도 덫은 끝난다.
    놓은 사람도 걸리고, 같은 라운드에 놓은 덫도 놓은 차례 뒤에 들어온 사람이 터뜨린다.
    이벤트는 들어간 것에 trap_sprung 이, 그 뒤에 HP 의 변화가 잇는다.
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

from app.rounds import prompt, trap_actions
from app.rounds.move_lines import describe_move, describe_trap_set, describe_travel
from app.rounds.narration_request import to_trap
from app.rounds.narrator import TrapNote, TrapSetNote, TravelNote
from app.rounds.router import visible_outcome
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import declare, going, outcome_of, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, give, held, post, read_table, table_url
from tests.test_table_items import take as take_away
from tests.test_table_map import open_duo, place_of, route
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

MIGRATION = pathlib.Path(__file__).parent.parent / 'migrations/versions/20261116_d6f8b0c2e4a7_traps.py'

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

# 피하기는 난이도를 비웠다. 규칙의 기본 난이도(보통 15)로 굴린다
TRAP = {
    'avoid': {'ability': 'dex'},
    'disarm': {'ability': 'dex', 'difficulty': 'hard'},
    'effects': [{'kind': 'damage', 'magnitude': 'light'}],
}
# 피하는 판정의 눈. 15 이상이면 피한다
DODGE, CAUGHT = 18, 3


@pytest.fixture
async def snares(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 물건 하나(올가미)를 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'
    snare = await post(client, url, me, name='올가미', keywords=[], content='올가미의 설명', kind='item')
    return {**lore, 'snare': snare}


def item_rules(world: dict, trap: dict | None = TRAP) -> list[dict]:
    """올가미는 덫이고 치유 물약은 덫이 아니다."""
    return [
        {'entry_id': world['snare']['id'], 'kind': 'gear', 'trap': trap},
        {'entry_id': world['potion']['id'], 'kind': 'consumable'},
    ]


def the_map(world: dict) -> dict:
    return {'start_place': world['gate']['id'], 'routes': [route(world['gate'], world['square'])]}


async def draft(client: AsyncClient, me: dict, world: dict, trap: dict | None = TRAP) -> dict:
    """덫을 적은 시나리오. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [world['lorebook']['id']],
        'items': item_rules(world, trap),
        **the_map(world),
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def start(
    client: AsyncClient, me: dict, friend: dict, world: dict, session: AsyncSession, trap: dict = TRAP
) -> dict:
    """덫을 적은 판으로 둘이 앉아 시작한 테이블. 나(기사)는 올가미 둘을 지녔다."""
    table = await open_duo(client, me, friend, world, items=item_rules(world, trap), **the_map(world))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    await give(session, started.json(), ME, world['snare'], 2)
    return started.json()


def setting(world: dict, item: str = 'snare') -> dict:
    return {'kind': 'set_trap', 'item': world[item]['id']}


def hp_of(table: dict, user_id: uuid.UUID) -> int:
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return member['sheet']['hp']


async def traps_of(session: AsyncSession) -> list[tuple]:
    """테이블의 덫들(놓은 사람, 끝난 까닭). 놓은 순서다."""
    rows = await session.execute(text('SELECT set_by, ended_reason FROM table_traps ORDER BY created_at, id'))
    return [tuple(row) for row in rows.all()]


# --- 시나리오 ---


async def test_a_trap_is_saved_published_and_shown(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession
):
    scenario = await draft(client, me, snares)

    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert published.status_code == status.HTTP_201_CREATED, published.text
    snare, potion = scenario['items']
    assert snare['trap'] == {
        'avoid': {'ability': 'dex', 'difficulty': None},
        'disarm': {'ability': 'dex', 'difficulty': 'hard'},
        'effects': [{'kind': 'damage', 'magnitude': 'light', 'nature': None}],
        'find': None,
    }
    assert potion['trap'] is None
    table = await start(client, me, friend, snares, session)
    shown = {item['name']: item['trap'] for item in table['items']}
    assert shown['올가미']['avoid'] == {'ability': 'dex', 'difficulty': None}
    assert shown['올가미']['effects'][0]['magnitude'] == 'light'
    assert shown['치유 물약'] is None


@pytest.mark.parametrize(
    'trap',
    [
        {**TRAP, 'effects': []},
        {**TRAP, 'effects': [{'kind': 'heal', 'magnitude': 'light'}]},
        {**TRAP, 'height': 3},
        {key: value for key, value in TRAP.items() if key != 'disarm'},
        {**TRAP, 'avoid': {'difficulty': 'hard'}},
    ],
    ids=['no-effects', 'heal', 'unknown-field', 'no-disarm', 'no-ability'],
)
async def test_a_misshaped_trap_is_refused(client: AsyncClient, me: dict, snares: dict, trap: dict):
    body = {'title': '성의 모험', 'items': item_rules(snares, trap)}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'trap',
    [
        {**TRAP, 'avoid': {'ability': 'luck'}},
        {**TRAP, 'disarm': {'ability': 'dex', 'difficulty': 'impossible'}},
        {**TRAP, 'effects': [{'kind': 'damage', 'magnitude': 'deadly'}]},
        {**TRAP, 'effects': [{'kind': 'injure', 'injury': 'cursed'}]},
    ],
    ids=['avoid-ability', 'disarm-difficulty', 'magnitude', 'injury'],
)
async def test_a_trap_must_fit_the_rules(client: AsyncClient, me: dict, snares: dict, trap: dict):
    scenario = await draft(client, me, snares, trap)

    response = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['item_trap_invalid']


# --- 놓기 ---


async def test_setting_a_trap_hides_it_here(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)

    await play(client, me, friend, table, narrated, mine=setting(snares))

    assert (await outcome_of(client, me, table, 1, ME))['trap_set'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'place': {'entry_id': snares['gate']['id'], 'name': '성문'},
        'entry_id': snares['snare']['id'],
        'name': '올가미',
        'set': True,
        'reason': None,
        'remaining': 1,
    }
    seen = await read_table(client, me, table)
    assert held(seen, ME) == [('올가미', 1)]
    # 숨겨 놓았다. 그 장소의 보이는 물건에 없다
    gate = next(place for place in seen['map']['places'] if place['entry_id'] == snares['gate']['id'])
    assert gate['items'] == []
    assert await traps_of(session) == [(ME, None)]
    (laid,) = await events_of(client, me, table, 'trap_set')
    acted = next(event for event in await events_of(client, me, table, 'player_action') if event['actor_id'] == str(ME))
    assert laid['caused_by_sequence'] == acted['sequence']
    # 누가 했는지는 행동의 이벤트에 있다. 내려놓기와 같이 user_id 를 싣지 않는다
    assert laid['actor_id'] is None
    assert laid['payload'] == {
        'round': 1,
        'character_name': '기사',
        'place': {'entry_id': snares['gate']['id'], 'name': '성문'},
        'entry_id': snares['snare']['id'],
        'name': '올가미',
        'set': True,
        'reason': None,
        'remaining': 1,
    }


@pytest.mark.parametrize('item', ['potion', 'nothing'])
async def test_only_a_held_trap_is_accepted(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession, item: str
):
    table = await start(client, me, friend, snares, session)
    await give(session, table, ME, snares['potion'], 1)
    world = {**snares, 'nothing': {'id': str(uuid.uuid4())}}

    response = await declare(client, me, table, setting(world, item))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_trap_not_held_is_refused(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession
):
    table = await start(client, me, friend, snares, session)

    response = await declare(client, friend, table, setting(snares))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


async def test_a_trap_off_the_map_is_refused(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession
):
    table = await start(client, me, friend, snares, session)
    await session.execute(text('UPDATE table_sheets SET place_id = NULL'))
    await session.commit()

    response = await declare(client, me, table, setting(snares))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'not_on_map' in response.text


async def test_a_trap_not_held_at_the_turn_is_not_set(
    client: AsyncClient, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    declared = await declare(client, me, table, setting(snares))
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await take_away(session, table, ME, snares['snare'])

    await declare(client, friend, table)
    await narrated()

    trap = (await outcome_of(client, me, table, 1, ME))['trap_set']
    assert (trap['set'], trap['reason'], trap['remaining']) == (False, 'not_held', 0)
    assert await traps_of(session) == []


# --- 터뜨리기 ---


async def test_the_setter_is_caught_too(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares))
    await play(client, me, friend, table, narrated, mine=going(snares['square']))
    # 피하는 판정의 눈 3(실패), 피해의 눈 2
    load_dice(app, [CAUGHT, 2])

    await play(client, me, friend, table, narrated, mine=going(snares['gate']))

    move = (await outcome_of(client, me, table, 3, ME))['move']
    assert move['moved'] is True
    (sprung,) = move['traps']
    assert (sprung['entry_id'], sprung['name'], sprung['set_by']) == (snares['snare']['id'], '올가미', str(ME))
    assert sprung['avoid'] == {
        'ability': 'dex',
        'difficulty': 'medium',
        'roll': CAUGHT,
        'modifier': 0,
        'total': CAUGHT,
        'target': 15,
        'success': False,
        'hindrance': None,
    }
    assert sprung['avoided'] is False
    assert (sprung['effect']['kind'], sprung['effect']['amount'], sprung['effect']['after']) == ('damage', 2, 8)
    seen = await read_table(client, me, table)
    assert (place_of(seen, ME), hp_of(seen, ME)) == (snares['gate']['id'], 8)
    assert await traps_of(session) == [(ME, 'sprung')]
    moved = (await events_of(client, me, table, 'character_moved'))[-1]
    (fired,) = await events_of(client, me, table, 'trap_sprung')
    (changed,) = await events_of(client, me, table, 'hp_changed')
    assert fired['caused_by_sequence'] == moved['sequence']
    assert changed['caused_by_sequence'] == fired['sequence']
    assert fired['payload'] == {
        'round': 3,
        'user_id': str(ME),
        'character_name': '기사',
        'place': {'entry_id': snares['gate']['id'], 'name': '성문'},
        'entry_id': snares['snare']['id'],
        'name': '올가미',
        'set_by': str(ME),
        'avoid': sprung['avoid'],
        'avoided': False,
    }


async def test_a_dodged_trap_is_gone_too(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['square']))
    load_dice(app, [DODGE])

    await play(client, me, friend, table, narrated, theirs=going(snares['gate']))

    (sprung,) = (await outcome_of(client, me, table, 2, FRIEND))['move']['traps']
    assert (sprung['avoided'], sprung['effect'], sprung['injured'], sprung['resources']) == (True, None, [], [])
    assert hp_of(await read_table(client, me, table), FRIEND) == 10
    assert await traps_of(session) == [(ME, 'sprung')]
    assert await events_of(client, me, table, 'hp_changed') == []

    # 끝난 덫은 다시 터지지 않는다
    await play(client, me, friend, table, narrated, theirs=going(snares['square']))
    await play(client, me, friend, table, narrated, theirs=going(snares['gate']))
    assert (await outcome_of(client, me, table, 4, FRIEND))['move']['traps'] == []


async def test_a_trap_set_this_round_springs_on_who_comes_after(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, theirs=going(snares['square']))
    load_dice(app, [CAUGHT, 1])

    # 앉은 순서로 기사가 먼저 놓고, 약사가 그 뒤에 들어온다
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['gate']))

    (sprung,) = (await outcome_of(client, me, table, 2, FRIEND))['move']['traps']
    assert (sprung['avoided'], sprung['set_by'], sprung['effect']['after']) == (False, str(ME), 9)
    (stored,) = (await session.execute(text('SELECT id FROM table_traps'))).scalars().all()
    assert sprung['trap_id'] == str(stored)


async def test_traps_set_in_one_round_keep_their_order(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await give(session, table, FRIEND, snares['snare'], 1)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=setting(snares))
    load_dice(app, [DODGE, DODGE])

    await play(client, me, friend, table, narrated, mine=going(snares['square']))
    await play(client, me, friend, table, narrated, mine=going(snares['gate']))

    first, second = (await outcome_of(client, me, table, 3, ME))['move']['traps']
    assert (first['set_by'], second['set_by']) == (str(ME), str(FRIEND))


async def test_two_traps_spring_in_the_order_they_were_set(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['square']))
    await play(client, me, friend, table, narrated, mine=setting(snares))
    load_dice(app, [DODGE, CAUGHT, 3])

    await play(client, me, friend, table, narrated, theirs=going(snares['gate']))

    first, second = (await outcome_of(client, me, table, 3, FRIEND))['move']['traps']
    assert (first['avoided'], second['avoided'], second['effect']['after']) == (True, False, 7)
    assert await traps_of(session) == [(ME, 'sprung'), (ME, 'sprung')]


async def test_a_poison_trap_leaves_its_injury(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    poison = {**TRAP, 'effects': [{'kind': 'injure', 'injury': 'poisoned'}]}
    table = await start(client, me, friend, snares, session, poison)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['square']))
    load_dice(app, [CAUGHT])

    await play(client, me, friend, table, narrated, theirs=going(snares['gate']))

    (sprung,) = (await outcome_of(client, me, table, 2, FRIEND))['move']['traps']
    assert (sprung['effect'], [one['injury'] for one in sprung['injured']]) == (None, ['poisoned'])
    stored = await session.execute(text('SELECT injury, source FROM table_injuries'))
    assert [tuple(row) for row in stored.all()] == [('poisoned', 'trap')]
    (fired,) = await events_of(client, me, table, 'trap_sprung')
    (gained,) = await events_of(client, me, table, 'injury_gained')
    assert gained['caused_by_sequence'] == fired['sequence']
    assert (gained['payload']['source'], gained['payload']['character_name']) == ('trap', '약사')


def test_a_dead_character_springs_no_more(monkeypatch: pytest.MonkeyPatch):
    member = SimpleNamespace(sheet=SimpleNamespace(place_id=uuid.uuid4()))
    armed = ['first', 'second', 'third']
    deaths = iter([False, True])
    monkeypatch.setattr(trap_actions.traps, 'hidden_at', lambda table, place: armed)
    monkeypatch.setattr(trap_actions.sheets, 'is_dead', lambda who: next(deaths))
    monkeypatch.setattr(trap_actions, 'spring_one', lambda judging, who, trap: {'trap': trap})

    sprung = trap_actions.spring_on_arrival(SimpleNamespace(table=None), member)

    assert sprung == [{'trap': 'first'}]


def test_a_move_without_traps_keeps_its_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(trap_actions, 'spring_on_arrival', lambda judging, member: [])
    moved = {'move': {'moved': True}}
    stayed = {'move': {'moved': False}}

    assert trap_actions.with_traps(None, None, moved) is moved
    monkeypatch.setattr(trap_actions, 'spring_on_arrival', lambda judging, member: pytest.fail('가지 못했다'))
    assert trap_actions.with_traps(None, None, stayed) is stayed


# --- 보이기와 서술과 되돌리기 ---


def test_a_hidden_trap_shift_is_left_out_for_others():
    shift = {'resource': 'mana', 'before': 3, 'after': 1, 'max': 7, 'user_id': str(ME), 'visibility': 'owner'}
    outcome = {'move': {'moved': True, 'traps': [{'name': '올가미', 'resources': [shift]}]}}

    assert visible_outcome(outcome, ME)['move']['traps'][0]['resources'] == [shift]
    assert visible_outcome(outcome, FRIEND)['move']['traps'][0]['resources'] == []
    assert outcome['move']['traps'][0]['resources'] == [shift]
    assert visible_outcome({'move': {'moved': True}}, FRIEND) == {'move': {'moved': True}}


def test_the_narration_lines_of_traps():
    caught = TrapNote(name='올가미', check='민첩', avoided=False)
    dodged = TrapNote(name='올가미', check='민첩', avoided=True)

    assert describe_travel(TravelNote('광장', '성문', True, traps=[caught, dodged])) == (
        '(간 곳: 광장 → 성문)(덫: 올가미. 민첩 판정에 실패해 걸렸다)(덫: 올가미. 민첩 판정에 성공해 피했다)'
    )
    assert describe_trap_set(TrapSetNote(name='올가미', set=True)) == '(덫 놓기: 올가미을(를) 숨겨 놓았다)'
    assert describe_trap_set(TrapSetNote(name='올가미', set=False)) == '(덫 놓기: 올가미을(를) 가지고 있지 않았다)'
    assert to_trap({'name': '올가미', 'avoid': {'ability': 'zzz'}, 'avoided': True}, None) == TrapNote(
        name='올가미', check='zzz', avoided=True
    )
    assert prompt.PROMPT_VERSION == 'narration-80'


async def test_the_narrator_hears_the_trap(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, snares: dict, session: AsyncSession, narrated
):
    recording = RecordingNarrator()
    app.state.narrator = recording
    table = await start(client, me, friend, snares, session)
    await play(client, me, friend, table, narrated, mine=setting(snares), theirs=going(snares['square']))
    load_dice(app, [CAUGHT, 2])

    await play(client, me, friend, table, narrated, theirs=going(snares['gate']))

    first, second = recording.requests
    mine = next(move for move in first.moves if move.character_name == '기사')
    assert mine.trap_set == TrapSetNote(name='올가미', set=True)
    theirs = next(move for move in second.moves if move.character_name == '약사')
    assert theirs.travel.traps == [TrapNote(name='올가미', check='민첩', avoided=False)]
    assert '(덫 놓기: 올가미을(를) 숨겨 놓았다)' in describe_move(mine)
    assert '(덫: 올가미. 민첩 판정에 실패해 걸렸다)' in describe_move(theirs)


def test_downgrade_strips_traps_from_item_rules():
    spec = importlib.util.spec_from_file_location('traps_migration', MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    rules = [{'entry_id': 'a', 'kind': 'gear', 'trap': TRAP}, {'entry_id': 'b', 'kind': 'gear'}]

    assert migration.without_traps(rules) == [{'entry_id': 'a', 'kind': 'gear'}, {'entry_id': 'b', 'kind': 'gear'}]
    assert migration.without_traps(None) == []
    assert rules[0]['trap'] == TRAP
