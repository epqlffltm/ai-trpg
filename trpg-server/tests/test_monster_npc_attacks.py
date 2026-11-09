# trpg-server/tests/test_monster_npc_attacks.py

"""
몬스터가 인물(NPC)도 치는 것(#254 NPC와 몬스터 사이, app/rounds/npc_victims.py)을 검증한다.

판은 여기서 만든다. 장소는 수로 입구(시작) 하나다. 입구에 수로 쥐(야수, 최대 HP 4)와 약사(인물, 중립)가 있다.
쥐는 물기(근력 보통, 가벼움 1d4)를 가진다. 캐릭터와 쥐와 약사의 능력치는 모두 10(보정 0)이다. 나 혼자 앉는다(엘프).
약사는 공격이 없어 차례를 받지 않는다. 주사위의 차례는 이렇다.
  차례의 주사위(엘프, 쥐) → 쥐의 대상(엘프와 약사, 2 면 약사) → 물기의 판정 → (맞히면) 피해 → (쓰러지면) 부상 표
  → 엘프의 판정.

보는 것.
  - 대상: 같은 장소의 인물도 친다. 캐릭터와 섞어 주사위로 고른다. 한편인 인물(시트의 allied_monsters)은 치지 않는다.
  - 맞으면: 인물이 피해를 입는다(npc_effect). 이벤트는 monster_attacked(맞은 인물) 뒤에 npc_changed 가 잇는다.
  - 쓰러짐과 마무리: 몬스터의 공격은 제압이라 HP 0 이면 쓰러진다. 쓰러진 인물은 다음 라운드부터 대상이고,
    맞히면 죽는다(finishing). 이번 라운드에 쓰러진 인물은 대상이 아니다. 몬스터가 쓰러뜨려도 드롭은 없다.
  - 게시: 한편인 몬스터가 시트를 적은 몬스터가 아니면 npc_ally_missing 이다. 같은 몬스터를 두 번 적으면 422 다.
  - 서술: 차례의 줄에 맞은 인물과 그 몸 상태가 붙는다. 쓰러진 인물을 쳤으면 "쓰러진" 이 붙는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import npc_victims
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_monster_turn
from app.tables.models import NpcStatus
from tests.narration_model import asset_body
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

pytestmark = pytest.mark.usefixtures('clean_tables')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
# 차례의 주사위. 쥐가 먼저 친다
LATE, EARLY = 1, 20
# 쥐의 대상. 엘프(앉은 순서)가 먼저, 그다음 약사(장면의 순서)다
ELF, HEALER = 1, 2
# 물기의 판정(보통, 목표 15)
MISS, HIT = 1, 20
# 부상 표의 눈. SRD5 의 1~10 은 아무 부상도 없다
NO_INJURY = 1
# 엘프의 판정의 눈(아무거나)
ANY = 10
CHECK = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def make_world(client: AsyncClient, me: dict) -> dict:
    """수로 입구와 약사가 든 로어북. 수로 쥐와 해골 병사가 든 도감. 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, url, me, name='수로 입구', kind='place'),
        'healer': await post(client, url, me, name='약사', kind='person'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def scenario_body(world: dict, healer_hp: int = 10, allied: list[str] | None = None) -> dict:
    """입구에 쥐 한 마리와 약사. allied 를 주면 약사의 시트에 한편인 몬스터로 적는다."""
    healer = {'entry_id': world['healer']['id'], 'sheet': make_sheet(max_hp=healer_hp)}
    if allied is not None:
        healer['allied_monsters'] = allied
    return {
        'title': '지하 수로',
        'rulebook_id': world['rulebook']['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'start_place': world['gate']['id'],
        'monster_sheets': [{'monster_id': world['rat']['id'], 'sheet': make_sheet(max_hp=4), 'attacks': [BITE]}],
        'encounters': [{'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 1}],
        'npc_sheets': [healer],
        'npc_places': [{'entry_id': world['healer']['id'], 'place_id': world['gate']['id']}],
    }


async def open_table(client: AsyncClient, me: dict, body: dict) -> dict:
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def healer_table(client: AsyncClient, me: dict, healer_hp: int = 10, allied: bool = False) -> dict:
    world = await make_world(client, me)
    body = scenario_body(world, healer_hp, [world['rat']['id']] if allied else None)
    return {**world, 'table': await open_table(client, me, body)}


async def act(client: AsyncClient, me: dict, world: dict, narrated) -> None:
    """나 혼자 앉은 테이블에서 선언해 라운드를 닫고 서술을 기다린다."""
    await declare(client, me, world['table'], '움직인다.', CHECK)
    await narrated()


async def rat_turn(session: AsyncSession, world: dict, number: int = 1) -> dict:
    turns = await turns_of(session, world['table'], number)
    return next(turn for turn in turns if turn['kind'] == 'monster')['outcome']


async def healer_state(session: AsyncSession, world: dict) -> tuple[str, int]:
    row = await session.execute(
        text('SELECT status, hp FROM table_npcs WHERE table_id = :table AND entry_id = :entry'),
        {'table': world['table']['id'], 'entry': world['healer']['id']},
    )
    status_, hp = row.one()
    return status_, hp


async def my_hp(session: AsyncSession, world: dict) -> int:
    query = text('SELECT hp FROM table_sheets WHERE table_id = :table ORDER BY number DESC LIMIT 1')
    return await session.scalar(query, {'table': world['table']['id']})


# --- 대상과 맞음 ---


async def test_a_monster_hits_a_bystander(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated):
    world = await healer_table(client, me)
    dice = load_dice(app, [LATE, EARLY, HEALER, HIT, 3, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    outcome = await rat_turn(session, world)
    assert (outcome['target_entry_id'], outcome['target_name'], outcome['finishing']) == (
        world['healer']['id'],
        '약사',
        False,
    )
    assert 'user_id' not in outcome
    assert (outcome['effect'], outcome['npc_effect']['amount'], outcome['npc_effect']['after']) == (None, 3, 7)
    assert await healer_state(session, world) == ('alive', 7)
    assert await my_hp(session, world) == 10
    seen = await events_of(client, me, world['table'])
    attacked = next(event for event in seen if event['type'] == 'monster_attacked')
    changed = next(event for event in seen if event['type'] == 'npc_changed')
    assert (attacked['payload']['target_name'], attacked['payload']['target_entry_id']) == (
        '약사',
        world['healer']['id'],
    )
    assert 'npc_effect' not in attacked['payload']
    assert changed['caused_by_sequence'] == attacked['sequence']
    assert (changed['payload']['name'], changed['payload']['amount']) == ('약사', 3)


async def test_a_miss_changes_nothing(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated):
    world = await healer_table(client, me)
    load_dice(app, [LATE, EARLY, HEALER, MISS, ANY])

    await act(client, me, world, narrated)

    outcome = await rat_turn(session, world)
    assert (outcome['success'], outcome['npc_effect']) == (False, None)
    assert await healer_state(session, world) == ('alive', 10)
    assert [event for event in await events_of(client, me, world['table']) if event['type'] == 'npc_changed'] == []


async def test_the_dice_can_still_pick_the_character(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await healer_table(client, me)
    load_dice(app, [LATE, EARLY, ELF, HIT, 3, ANY])

    await act(client, me, world, narrated)

    outcome = await rat_turn(session, world)
    assert (outcome['character_name'], 'target_entry_id' in outcome) == ('엘프', False)
    assert await my_hp(session, world) == 7
    assert await healer_state(session, world) == ('alive', 10)


async def test_an_ally_of_the_monster_is_left_alone(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await healer_table(client, me, allied=True)
    # 약사는 쥐와 한편이다. 칠 것이 엘프뿐이라 대상의 주사위가 없다
    dice = load_dice(app, [LATE, EARLY, MISS, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    assert (await rat_turn(session, world))['character_name'] == '엘프'


# --- 쓰러짐과 마무리 ---


async def test_a_downed_bystander_is_finished_the_next_round(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await healer_table(client, me, healer_hp=2)
    # 피해 2 로 쓰러진다(큰 타격이라 부상 표를 한 번 굴린다). 몬스터가 쓰러뜨려 드롭은 없다
    load_dice(app, [LATE, EARLY, HEALER, HIT, 2, NO_INJURY, ANY])
    await act(client, me, world, narrated)
    downed = await rat_turn(session, world)
    assert (downed['npc_effect']['status'], downed['npc_effect']['lethal'], 'drop' in downed) == (
        'downed',
        False,
        False,
    )
    assert await healer_state(session, world) == ('downed', 0)
    # 다음 라운드. 쓰러진 약사도 대상이다. 맞히면 죽는다(죽으면 부상 표가 없다)
    dice = load_dice(app, [LATE, EARLY, HEALER, HIT, 1, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    finished = await rat_turn(session, world, 2)
    assert (finished['finishing'], finished['npc_effect']['lethal'], finished['npc_effect']['status']) == (
        True,
        True,
        'dead',
    )
    assert await healer_state(session, world) == ('dead', 0)
    attacked = [event for event in await events_of(client, me, world['table']) if event['type'] == 'monster_attacked']
    assert attacked[-1]['payload']['finishing'] is True


async def test_a_dead_bystander_is_no_target(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await healer_table(client, me)
    await session.execute(
        text("UPDATE table_npcs SET status = 'dead', hp = 0 WHERE table_id = :id"), {'id': world['table']['id']}
    )
    await session.commit()
    dice = load_dice(app, [LATE, EARLY, MISS, ANY])

    await act(client, me, world, narrated)

    assert dice.remaining == 0
    assert (await rat_turn(session, world))['character_name'] == '엘프'


# --- 게시 ---


async def test_an_ally_must_be_a_sheeted_monster(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(world, allied=[world['skeleton']['id']]))

    url = f'{SCENARIOS_URL}/{scenario["id"]}/versions'
    response = await client.post(url, json=asset_body(url, {}), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == ['npc_ally_missing']


async def test_the_scenario_keeps_the_allies_and_refuses_twice_the_same(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    rat = world['rat']['id']
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(world, allied=[rat]))
    body = scenario_body(world, allied=[rat, rat])

    refused = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}', json={'npc_sheets': body['npc_sheets']}, headers=me
    )

    assert scenario['npc_sheets'][0]['allied_monsters'] == [rat]
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 서술 ---


def test_the_turn_line_tells_the_bystander_and_its_state():
    hit = {
        'attack': {'name': '물기'},
        'target_entry_id': str(uuid.uuid4()),
        'target_name': '약사',
        'finishing': False,
        'success': True,
        'effect': None,
        'npc_effect': {'kind': 'damage', 'name': '약사', 'amount': 3, 'condition': '다침', 'injury_roll': None},
    }
    finished = {
        **hit,
        'finishing': True,
        'npc_effect': {**hit['npc_effect'], 'amount': 2, 'condition': '죽음'},
    }

    lines = [describe_monster_turn(to_monster_turn({'name': '수로 쥐', 'outcome': one})) for one in (hit, finished)]

    assert lines == [
        '수로 쥐: 약사에게 물기 (맞음) → 약사 피해 3 (다침)',
        '수로 쥐: 쓰러진 약사에게 물기 (맞음) → 약사 피해 2 (죽음)',
    ]


# --- 작은 함수들 ---


def person(entry_id: uuid.UUID, status_: str, place_id: uuid.UUID | None, allied: list[uuid.UUID] | None = None):
    definition = None if allied is None else SimpleNamespace(allied_monsters=allied)
    npc = SimpleNamespace(status=NpcStatus(status_), place_id=place_id)
    return SimpleNamespace(entry_id=entry_id, npc=npc, definition=definition, name='누군가')


def test_who_a_monster_may_strike():
    here, there, rat = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    standing, fallen_before, fallen_now, dead = (
        person(uuid.uuid4(), one, here)
        for one in (
            'alive',
            'downed',
            'downed',
            'dead',
        )
    )
    elsewhere, unplaced = person(uuid.uuid4(), 'alive', there), person(uuid.uuid4(), 'alive', None)
    friend = person(uuid.uuid4(), 'alive', here, allied=[rat])
    stranger = person(uuid.uuid4(), 'alive', here, allied=[uuid.uuid4()])
    cast = [standing, fallen_before, fallen_now, dead, elsewhere, unplaced, friend, stranger]
    judging = SimpleNamespace(cast=cast, npcs_downed_at_start=frozenset({fallen_before.entry_id}))
    monster = SimpleNamespace(state=SimpleNamespace(place_id=here), definition=SimpleNamespace(id=rat))

    assert npc_victims.victims_of(judging, monster) == [standing, fallen_before, stranger]
