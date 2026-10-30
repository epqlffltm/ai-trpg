# trpg-server/tests/test_foe_traps.py

"""
몬스터와 싸우는 인물(NPC)이 덫을 밟는 것(#806 ②-b, app/rounds/foe_traps.py)을 검증한다.

판은 여기서 만든다. 장소는 수로 입구(시작) 하나다. 입구에 미리 놓인 올가미가 있다(시나리오의 traps).
올가미의 피하기는 민첩 보통(15), 효과는 가벼운 피해(1d4)다. 캐릭터와 쥐와 인물의 능력치는 모두 10(보정 0)이다.
  - 쥐 판: 입구에 수로 쥐(야수, 최대 HP 4)가 있다. 물기(근력 보통, 가벼움)를 가진다.
    동전 하나를 지녔다(쓰러지면 나온다).
  - 인물 판: 입구에 악역영애(적대, 최대 HP 10)가 있다. 부채 후리기(민첩 보통, 가벼움)를 가진다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 차례가 같은 점수면 앉은 사람, 몬스터의 순서로 차례의 주사위를 굴린다.

보는 것.
  - 몬스터: 차례에 공격을 굴린 뒤 그 장소의 덫 하나를 밟는다. 못 피하면 피해를 입는다. 피하든 못 피하든 덫은 끝난다.
    처음 쓰러졌으면 드롭이 나온다. 이벤트는 공격(monster_attacked)에 trap_sprung 이, 그 뒤에 마리의 변화가 잇는다.
    찾아낸 덫도 밟는다. 덫이 없거나 다 터졌으면 밟지 않는다.
  - 인물: 장소가 있는 싸우는 인물도 같다(npc_attacked 에 trap_sprung, npc_changed).
  - 서술: 차례의 줄 끝에 밟은 덫이 붙는다.
"""

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import foe_traps
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_monster_turn
from app.rounds.narrator import MonsterTurnNote
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
    post,
    table_url,
    turns_of,
)
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
SWIPE = {'name': '부채 후리기', 'ability': 'dex', 'difficulty': 'medium', 'harm': 'light'}
TRAP = {
    'avoid': {'ability': 'dex'},
    'disarm': {'ability': 'dex', 'difficulty': 'hard'},
    'effects': [{'kind': 'damage', 'magnitude': 'light'}],
}
# 차례의 주사위. 몬스터와 인물이 먼저 친다
LATE, EARLY = 1, 20
# 공격의 눈(빗나감), 피하는 판정의 눈
MISS, CAUGHT, DODGE = 1, 3, 18
# 판정하는 행동의 눈(아무거나)
ANY = 10
CHECK = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def make_world(client: AsyncClient, me: dict) -> dict:
    """수로 입구와 올가미와 동전, 악역영애가 든 로어북. 수로 쥐가 든 도감. 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, url, me, name='수로 입구', kind='place'),
        'snare': await post(client, url, me, name='올가미', kind='item'),
        'coin': await post(client, url, me, name='동전', kind='item'),
        'lady': await post(client, url, me, name='악역영애', kind='person'),
        'rat': await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='수로 쥐', kind='beast'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def base(world: dict, traps: list[dict]) -> dict:
    return {
        'title': '지하 수로',
        'rulebook_id': world['rulebook']['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'start_place': world['gate']['id'],
        'items': [{'entry_id': world['snare']['id'], 'kind': 'gear', 'trap': TRAP}],
        'traps': traps,
    }


def snare_at_gate(world: dict, count: int = 1, known: bool = False) -> list[dict]:
    return [{'place_id': world['gate']['id'], 'entry_id': world['snare']['id'], 'known': known}] * count


async def open_table(client: AsyncClient, me: dict, body: dict) -> dict:
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def rat_table(client: AsyncClient, me: dict, traps: int = 1, rat_hp: int = 4, known: bool = False) -> dict:
    """쥐 판의 테이블. 입구에 올가미 traps 개, 동전을 지닌 쥐 한 마리."""
    world = await make_world(client, me)
    rat = {
        'monster_id': world['rat']['id'],
        'sheet': make_sheet(max_hp=rat_hp),
        'attacks': [BITE],
        'inventory': [{'entry_id': world['coin']['id'], 'count': 1, 'chance': 100}],
    }
    body = {
        **base(world, snare_at_gate(world, traps, known)),
        'monster_sheets': [rat],
        'encounters': [{'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 1}],
    }
    return {**world, 'table': await open_table(client, me, body)}


async def lady_table(client: AsyncClient, me: dict) -> dict:
    """인물 판의 테이블. 입구에 올가미 하나, 적대하는 악역영애가 입구에 있다."""
    world = await make_world(client, me)
    lady = {'entry_id': world['lady']['id'], 'sheet': make_sheet(), 'attitude': 'hostile', 'attacks': [SWIPE]}
    body = {
        **base(world, snare_at_gate(world)),
        'npc_sheets': [lady],
        'npc_places': [{'entry_id': world['lady']['id'], 'place_id': world['gate']['id']}],
    }
    return {**world, 'table': await open_table(client, me, body)}


async def act(client: AsyncClient, me: dict, world: dict, narrated, action: dict | None = CHECK) -> None:
    """나 혼자 앉은 테이블에서 선언해 라운드를 닫고 서술을 기다린다."""
    await declare(client, me, world['table'], '움직인다.', action)
    await narrated()


def foe_turn(turns: list[dict], kind: str) -> dict:
    return next(turn for turn in turns if turn['kind'] == kind)


async def trap_ends(session: AsyncSession) -> list[str | None]:
    rows = await session.execute(text('SELECT ended_reason FROM table_traps ORDER BY created_at, id'))
    return list(rows.scalars().all())


async def events(client: AsyncClient, me: dict, world: dict) -> list[dict]:
    return await events_of(client, me, world['table'])


# --- 몬스터 ---


async def test_an_attacking_monster_steps_on_a_trap(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await rat_table(client, me)
    # 차례의 주사위(엘프, 쥐), 쥐의 물기(빗나감), 쥐의 피하는 판정(실패), 덫의 피해, 엘프의 판정
    dice = load_dice(app, [LATE, EARLY, MISS, CAUGHT, 1, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    stepped = foe_turn(await turns_of(session, world['table']), 'monster')['outcome']['trap']
    assert (stepped['entry_id'], stepped['name'], stepped['set_by']) == (world['snare']['id'], '올가미', None)
    assert stepped['place'] == {'entry_id': world['gate']['id'], 'name': '수로 입구'}
    assert (stepped['avoid']['ability'], stepped['avoid']['roll'], stepped['avoided']) == ('dex', CAUGHT, False)
    assert (stepped['monster_effect']['amount'], stepped['monster_effect']['after']) == (1, 3)
    assert (stepped['injured'], stepped['resources'], 'drop' in stepped) == ([], [], False)
    assert await trap_ends(session) == ['sprung']
    seen = await events(client, me, world)
    attacked = next(event for event in seen if event['type'] == 'monster_attacked')
    fired = next(event for event in seen if event['type'] == 'trap_sprung')
    changed = next(event for event in seen if event['type'] == 'monster_changed')
    stored = await session.scalar(text("SELECT payload FROM table_events WHERE type = 'monster_attacked'"))
    assert 'trap' not in stored
    assert fired['caused_by_sequence'] == attacked['sequence']
    assert changed['caused_by_sequence'] == fired['sequence']
    assert (fired['payload']['monster_name'], fired['payload']['avoided']) == ('수로 쥐', False)
    assert 'monster_id' in fired['payload']


async def test_a_dodging_monster_still_springs_it(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await rat_table(client, me)
    load_dice(app, [LATE, EARLY, MISS, DODGE, ANY])

    await act(client, me, world, narrated)

    stepped = foe_turn(await turns_of(session, world['table']), 'monster')['outcome']['trap']
    assert (stepped['avoided'], stepped['monster_effect']) == (True, None)
    assert await trap_ends(session) == ['sprung']
    assert [event for event in await events(client, me, world) if event['type'] == 'monster_changed'] == []


async def test_one_trap_a_turn_and_none_once_gone(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await rat_table(client, me, traps=2)
    load_dice(app, [LATE, EARLY, MISS, DODGE, ANY])
    await act(client, me, world, narrated)
    assert await trap_ends(session) == ['sprung', None]
    load_dice(app, [LATE, EARLY, MISS, DODGE, ANY])
    await act(client, me, world, narrated)
    assert await trap_ends(session) == ['sprung', 'sprung']
    dice = load_dice(app, [LATE, EARLY, MISS, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    assert 'trap' not in foe_turn(await turns_of(session, world['table'], 3), 'monster')['outcome']


async def test_a_monster_steps_on_a_trap_the_party_knows(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await rat_table(client, me, known=True)
    load_dice(app, [LATE, EARLY, MISS, DODGE, ANY])

    await act(client, me, world, narrated)

    assert foe_turn(await turns_of(session, world['table']), 'monster')['outcome']['trap']['avoided'] is True


async def test_a_monster_downed_by_a_trap_drops_what_it_carried(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await rat_table(client, me, rat_hp=1)
    # 덫의 피해 1 로 쓰러진다. 쓰러지면 부상 표(1, 부상 없음)를 굴리고, 드롭을 굴리고(100% 라 굴리지 않는다)
    # 받을 사람(혼자라 굴리지 않는다)을 정한다. 쥐가 쓰러져 엘프의 판정만 남는다
    load_dice(app, [LATE, EARLY, MISS, CAUGHT, 1, 1, ANY, ANY, ANY])

    await act(client, me, world, narrated)

    stepped = foe_turn(await turns_of(session, world['table']), 'monster')['outcome']['trap']
    assert stepped['monster_effect']['after'] == 0
    assert [(thing['name'], thing['count']) for thing in stepped['drop']['items']] == [('동전', 1)]
    gained = [event for event in await events(client, me, world) if event['type'] == 'items_gained']
    assert [event['payload']['name'] for event in gained] == ['동전']


# --- 인물 ---


async def test_a_fighting_npc_steps_on_a_trap(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await lady_table(client, me)
    # 라운드 1: 엘프가 악역영애를 친다(빗나감). 싸움이 붙는다. 아직 차례가 없다
    punch = {**CHECK, 'ability': 'str', 'harm': 'moderate', 'npc': world['lady']['id']}
    load_dice(app, [MISS])
    await act(client, me, world, narrated, punch)
    # 라운드 2: 악역영애의 부채 후리기(빗나감), 피하는 판정(실패), 덫의 피해
    dice = load_dice(app, [MISS, CAUGHT, 2])

    await act(client, me, world, narrated, None)

    assert dice.remaining == 0
    stepped = foe_turn(await turns_of(session, world['table'], 2), 'npc')['outcome']['trap']
    assert (stepped['avoided'], stepped['npc_effect']['amount'], stepped['npc_effect']['after']) == (False, 2, 8)
    assert await trap_ends(session) == ['sprung']
    seen = await events(client, me, world)
    attacked = next(event for event in seen if event['type'] == 'npc_attacked')
    fired = next(event for event in seen if event['type'] == 'trap_sprung')
    changed = next(event for event in seen if event['type'] == 'npc_changed' and event['payload']['round'] == 2)
    assert fired['caused_by_sequence'] == attacked['sequence']
    assert changed['caused_by_sequence'] == fired['sequence']
    assert (fired['payload']['npc_name'], fired['payload']['npc_id']) == ('악역영애', world['lady']['id'])


async def test_a_dodging_npc_still_springs_it(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await lady_table(client, me)
    punch = {**CHECK, 'ability': 'str', 'harm': 'moderate', 'npc': world['lady']['id']}
    load_dice(app, [MISS])
    await act(client, me, world, narrated, punch)
    dice = load_dice(app, [MISS, DODGE])

    await act(client, me, world, narrated, None)

    assert dice.remaining == 0
    stepped = foe_turn(await turns_of(session, world['table'], 2), 'npc')['outcome']['trap']
    assert (stepped['avoided'], stepped['npc_effect'], stepped['injured']) == (True, None, [])
    assert await trap_ends(session) == ['sprung']


# --- 서술 ---


async def test_the_narrator_hears_the_monster_trapped(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    recording = RecordingNarrator()
    app.state.narrator = recording
    world = await rat_table(client, me)
    load_dice(app, [LATE, EARLY, MISS, CAUGHT, 1, ANY])

    await act(client, me, world, narrated)

    (request,) = recording.requests
    (monster,) = [turn.monster for turn in request.turns if turn.monster is not None]
    assert (monster.trap, monster.trapped) == ('올가미', True)


def test_the_turn_line_tells_the_trap():
    caught = MonsterTurnNote(name='수로 쥐', attack='물기', target='엘프', hit=False, trap='올가미', trapped=True)
    dodged = MonsterTurnNote(name='수로 쥐', attack='물기', target='엘프', hit=False, trap='올가미', trapped=False)
    plain = MonsterTurnNote(name='수로 쥐', attack='물기', target='엘프', hit=False)

    assert describe_monster_turn(caught) == '수로 쥐: 엘프에게 물기 (빗나감) [덫: 올가미에 걸림]'
    assert describe_monster_turn(dodged) == '수로 쥐: 엘프에게 물기 (빗나감) [덫: 올가미을(를) 피함]'
    assert describe_monster_turn(plain) == '수로 쥐: 엘프에게 물기 (빗나감)'
    turn = {
        'name': '수로 쥐',
        'outcome': {
            'attack': BITE,
            'character_name': '엘프',
            'success': False,
            'effect': None,
            'trap': {'name': '올가미', 'avoided': True},
        },
    }
    assert (to_monster_turn(turn).trap, to_monster_turn(turn).trapped) == ('올가미', False)
    assert to_monster_turn({**turn, 'outcome': {**turn['outcome'], 'trap': None}}).trap is None


def test_a_turn_without_a_trap_keeps_its_shape():
    outcome = {'attack': BITE}

    assert foe_traps.with_trap(outcome, None) is outcome
    assert foe_traps.with_trap(outcome, {'name': '올가미'}) == {'attack': BITE, 'trap': {'name': '올가미'}}
    assert foe_traps.first_trap(None, None) is None
