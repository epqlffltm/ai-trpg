# game-server/tests/test_npc_steals.py

"""
NPC 가 지닌 물건을 훔치는 행동(steal 의 npc, #457 의 2/2, app/rounds/steals.py)을 검증한다.

판은 test_npc_items.py 의 것이다. 스타팅에 악역영애가 나오고, 부채(레어, 장비)와 금화 5개(소지품)를 지녔다.
룰북은 SRD5 다. 훔치기는 민첩으로 보통(15)에 도전하고, 대상의 지혜를 본다. 시트의 능력치는 모두 10(보정 0)이다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 행동의 모양: monster 와 npc 중 하나만 적는다. 판의 on_caught 는 hostile 과 fight 뿐이다(판 형식 39).
  - 받을 때: 장면의 인물이 아니거나, 그 인물이 그 물건을 지니지 않았으면 거부한다.
  - 목표값: 몬스터와 같다. 장비, 등급, 둔함, 싸움 전, 다른 사람과 싸우는 중. 타입은 없다.
    NPC 를 타격으로 겨눈 판정은 싸움이다(빗나가도). 회복이나 타격 없는 판정은 아니다.
  - 성공: 줄을 통째로 갖고 인물 목록에서 빠진다. items_gained 의 대상이 그 인물이다.
  - 들킴: 늘 적대가 된다(이미 적대면 그대로). on_caught 가 fight 면 싸운 것도 된다. 이벤트와 서술에 남는다.
  - 차례가 왔을 때 그 인물이 죽었거나 그 물건이 없으면 굴리지 않는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_38
from app.engine.action import StealAction
from app.rounds.checks import mark_npc_attack
from app.rounds.move_lines import describe_steal
from app.rounds.narrator import StealNote
from app.rounds.steals import fights_when_caught
from app.tables.models import NpcStatus, TableNpc
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.test_npc_actions import (
    FAIL,
    PASS,
    PUNCH,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    events_of,
    load_dice,
    people,
    post,
    punch,
    table_url,
)
from tests.test_npc_items import lady_sheet, make_lore, make_scenario, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STEAL = '악역영애의 품을 슬쩍 더듬는다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def start(client: AsyncClient, me: dict, *others: dict, **sheet_fields) -> dict:
    """악역영애(sheet_fields 로 시트의 칸을 바꾼다)가 나오는 시나리오로 테이블을 시작한다. 나와 others 가 앉는다."""
    lore = await make_lore(client, me)
    scenario = await make_scenario(client, me, lore, lady_sheet(lore, **sheet_fields))
    published = await publish(client, me, scenario)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**lore, 'table': table}


def steal(world: dict, item: str, npc: str = 'lady') -> dict:
    return {'kind': 'steal', 'npc': world[npc]['id'], 'item': world[item]['id']}


async def send(client: AsyncClient, headers: dict, world: dict, action: dict, content: str = STEAL):
    body = {'content': content, 'action': action}
    return await client.put(table_url(world['table'], '/rounds/current/declaration'), json=body, headers=headers)


async def outcome(client: AsyncClient, me: dict, world: dict, number: int = 1, user_id: uuid.UUID = ME) -> dict:
    response = await client.get(table_url(world['table'], f'/rounds/{number}'), headers=me)
    declaration = next(item for item in response.json()['declarations'] if item['user_id'] == str(user_id))
    return declaration['outcome']


async def steal_now(client, app, me, world, item: str, rolls: list[int], narrated, number: int = 1) -> dict:
    """나 혼자 앉은 테이블에서 악역영애에게서 훔치고 라운드를 닫는다. 결과의 steal 을 돌려준다."""
    load_dice(app, rolls)
    response = await send(client, me, world, steal(world, item))
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()
    return (await outcome(client, me, world, number))['steal']


async def lady_state(session: AsyncSession, world: dict) -> TableNpc:
    query = select(TableNpc).where(
        TableNpc.table_id == uuid.UUID(world['table']['id']), TableNpc.entry_id == uuid.UUID(world['lady']['id'])
    )
    return await session.scalar(query.execution_options(populate_existing=True))


# --- 행동의 모양과 받을 때 ---


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'steal', 'item': str(uuid.uuid4())},
        {'kind': 'steal', 'item': str(uuid.uuid4()), 'monster': str(uuid.uuid4()), 'npc': str(uuid.uuid4())},
    ],
)
def test_a_steal_names_exactly_one_victim(body: dict):
    with pytest.raises(ValidationError):
        StealAction.model_validate(body)


async def test_an_unknown_reaction_is_refused(client: AsyncClient, me: dict[str, str]):
    lore = await make_lore(client, me)
    body = {'title': '추격전', 'npc_sheets': [lady_sheet(lore, on_caught='flee')]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('change', 'detail'),
    [
        # 드워프는 장면에 나오지 않았다
        (lambda world: steal(world, 'coins', npc='dwarf'), 'action.npc 가 이번 장면의 인물이 아닙니다.'),
        # 악역영애는 고속도로를 지니지 않았다
        (
            lambda world: {**steal(world, 'coins'), 'item': world['highway']['id']},
            'action.item 이 그 몬스터나 인물이 지금 지닌 물건이 아닙니다.',
        ),
    ],
)
async def test_what_cannot_be_stolen_is_refused(client: AsyncClient, me: dict[str, str], change, detail: str):
    world = await start(client, me)

    response = await send(client, me, world, change(world))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == detail


# --- 목표값 ---


@pytest.mark.parametrize(
    ('item', 'fields', 'target', 'factors'),
    [
        # 보통 15, 싸움 전 -3
        ('coins', {}, 12, ['unwary']),
        # 장비 +5, 레어는 노말에서 한 단계 +2
        ('fan', {}, 19, ['equipped', 'rarity', 'unwary']),
        # 둔하다고 적었으면 -3. NPC 는 타입이 없어 둔한 타입은 걸리지 않는다
        ('coins', {'dull': True}, 9, ['dull', 'unwary']),
    ],
)
async def test_the_target_is_worked_out_like_for_a_monster(
    client: AsyncClient, app: FastAPI, me: dict, narrated, item: str, fields: dict, target: int, factors: list[str]
):
    world = await start(client, me, **fields)

    stolen = await steal_now(client, app, me, world, item, [1], narrated)

    assert (stolen['check']['target'], stolen['factors']) == (target, factors)


async def test_a_hit_aimed_at_the_npc_starts_a_fight(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me)
    # 빗나가도 싸움이다
    load_dice(app, [FAIL])
    await send(client, me, world, punch(world['lady']['id']), content=PUNCH)
    await narrated()
    assert (await lady_state(session, world)).fought_round == 1

    stolen = await steal_now(client, app, me, world, 'coins', [1], narrated, number=2)

    assert (stolen['check']['target'], stolen['factors']) == (15, [])


async def test_an_npc_fighting_someone_else_is_distracted(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start(client, me, friend)
    # 엘프가 먼저 주먹을 날리고(빗나감), 드워프 기사가 그 틈에 훔친다
    load_dice(app, [FAIL, 1])
    await send(client, me, world, punch(world['lady']['id']), content=PUNCH)
    await send(client, friend, world, steal(world, 'coins'))
    await narrated()

    stolen = (await outcome(client, me, world, 1, FRIEND))['steal']

    # 싸움은 이미 붙었다(싸움 전이 아니다). 다른 사람과 싸우는 중이라 -2
    assert (stolen['check']['target'], stolen['factors']) == (13, ['distracted'])


# --- 성공 ---


async def test_a_success_takes_the_whole_line(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)

    stolen = await steal_now(client, app, me, world, 'coins', [12], narrated)

    assert stolen == {
        'user_id': str(ME),
        'character_name': '엘프',
        'monster_id': None,
        'monster_name': None,
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
        'entry_id': world['coins']['id'],
        'name': '금화',
        'check': {'roll': 12, 'modifier': 0, 'total': 12, 'target': 12, 'success': True},
        'hindrance': None,
        'factors': ['unwary'],
        'stolen': True,
        'count': 5,
        'left': 0,
        'total': 5,
        'reason': None,
        'fight': False,
        'attitude_change': None,
    }
    (lady,) = (await people(client, me, world['table']))['people']
    assert [(thing['name'], thing['count']) for thing in lady['items']] == [('부채', 1)]
    assert lady['attitude'] == 'neutral'


async def test_the_gain_names_the_npc(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    await steal_now(client, app, me, world, 'coins', [12], narrated)

    (attempted,) = await events_of(client, me, world['table'], 'steal_attempted')
    (gained,) = await events_of(client, me, world['table'], 'items_gained')

    assert (attempted['payload']['npc_id'], attempted['payload']['npc_name']) == (world['lady']['id'], '악역영애')
    assert gained['caused_by_sequence'] == attempted['sequence']
    assert {key: gained['payload'][key] for key in ('source', 'npc_id', 'npc_name', 'count')} == {
        'source': 'steal',
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
        'count': 5,
    }
    assert 'monster_id' not in gained['payload']


async def test_a_second_thief_finds_the_line_gone(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)
    load_dice(app, [20])
    await send(client, me, world, steal(world, 'coins'))
    await send(client, friend, world, steal(world, 'coins'))
    await narrated()

    theirs = (await outcome(client, me, world, 1, FRIEND))['steal']

    assert (theirs['stolen'], theirs['check'], theirs['reason'], theirs['fight']) == (False, None, 'gone', False)


async def test_an_npc_killed_earlier_in_the_round_is_not_rolled_for(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start(client, me, friend)
    # 엘프가 먼저 죽인다(큰 피해 2d8, 죽이려는 타격). 처음 쓰러졌으니 금화의 드롭을 굴리고(51, 안 나옴)
    # 나온 부채를 받을 사람을 둘 중에서 고른다(1). 드워프 기사의 훔치기는 굴리지 않는다
    load_dice(app, [PASS, 8, 8, 51, 1])
    await send(client, me, world, punch(world['lady']['id'], 'heavy', lethal=True), content=PUNCH)
    await send(client, friend, world, steal(world, 'coins'))
    await narrated()

    theirs = await outcome(client, me, world, 1, FRIEND)

    assert theirs == {
        'target_gone': {'monster_id': None, 'npc_id': world['lady']['id'], 'name': '악역영애', 'reason': 'dead'}
    }


# --- 들킴 ---


async def test_a_caught_thief_makes_the_npc_hostile(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me)

    stolen = await steal_now(client, app, me, world, 'coins', [11], narrated)

    assert (stolen['stolen'], stolen['fight']) == (False, False)
    assert stolen['attitude_change'] == {'previous': 'neutral', 'attitude': 'hostile', 'reason': 'caught_stealing'}
    lady = await lady_state(session, world)
    # 시트에 적지 않았으면 적대만 한다. 싸움은 붙지 않는다
    assert (lady.attitude, lady.fought_round) == ('hostile', None)
    (attempted,) = await events_of(client, me, world['table'], 'steal_attempted')
    (changed,) = await events_of(client, me, world['table'], 'npc_attitude_changed')
    assert changed['caused_by_sequence'] == attempted['sequence']
    assert changed['payload'] == {
        'round': 1,
        'entry_id': world['lady']['id'],
        'name': '악역영애',
        'previous': 'neutral',
        'attitude': 'hostile',
        'reason': 'caught_stealing',
    }
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert (
        '(훔치기: 악역영애 에게서 금화을(를) 훔치다 들켰다. 악역영애 이(가) 적대한다)'
        in narrations[-1]['payload']['text']
    )


async def test_a_fighter_starts_a_fight_when_caught(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me, on_caught='fight')

    stolen = await steal_now(client, app, me, world, 'coins', [11], narrated)

    assert stolen['fight'] is True
    assert (await lady_state(session, world)).fought_round == 1
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '악역영애 이(가) 적대한다. 싸움이 붙었다)' in narrations[-1]['payload']['text']
    # 싸움이 붙었으니 다음에는 싸움 전이 아니다
    again = await steal_now(client, app, me, world, 'coins', [1], narrated, number=2)
    assert (again['check']['target'], again['factors']) == (15, [])


async def test_an_already_hostile_npc_stays_hostile(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me, attitude='hostile')

    stolen = await steal_now(client, app, me, world, 'coins', [11], narrated)

    assert stolen['attitude_change'] is None
    assert await events_of(client, me, world['table'], 'npc_attitude_changed') == []
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '악역영애 은(는) 이미 적대하고 있다)' in narrations[-1]['payload']['text']


# --- 판 ---


def test_an_old_snapshot_reads_everyone_as_only_turning_hostile():
    sheet = {'entry_id': str(uuid.uuid4()), 'sheet': SHEET, 'attitude': 'neutral', 'equipment': [], 'inventory': []}
    document = {'format': 38, 'npc_sheets': [sheet]}

    upgraded = upgrade_from_38(document)

    assert upgraded['format'] == 39
    assert upgraded['npc_sheets'] == [{**sheet, 'on_caught': 'hostile'}]
    assert UPGRADES[38] is upgrade_from_38


# --- DB 를 쓰지 않는 작은 함수들 ---


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            StealNote(victim='악역영애', name='금화', count=5, stolen=True, caught=False, npc=True),
            '(훔치기: 악역영애 에게서 금화 5개를 몰래 빼냈다)',
        ),
        (
            StealNote(victim='악역영애', name='금화', count=0, stolen=False, caught=True, npc=True, hostile=True),
            '(훔치기: 악역영애 에게서 금화을(를) 훔치다 들켰다. 악역영애 이(가) 적대한다)',
        ),
        (
            StealNote(victim='악역영애', name='부채', count=0, stolen=False, caught=True, npc=True, fight=True),
            '(훔치기: 악역영애 에게서 부채을(를) 훔치다 들켰다. 악역영애 은(는) 이미 적대하고 있다. 싸움이 붙었다)',
        ),
        (
            StealNote(victim='수로 쥐', name='송곳니', count=0, stolen=False, caught=True, fight=True),
            '(훔치기: 수로 쥐 에게서 송곳니을(를) 훔치다 들켰다. 수로 쥐 이(가) 노린다)',
        ),
    ],
)
def test_the_steal_line(note: StealNote, line: str):
    assert describe_steal(note) == line


def test_without_a_sheet_a_person_only_turns_hostile():
    assert fights_when_caught(SimpleNamespace(definition=None)) is False


def judging_with(npc: TableNpc) -> SimpleNamespace:
    person = SimpleNamespace(entry_id=npc.entry_id, npc=npc)
    return SimpleNamespace(cast=[person], fights={}, round_number=2)


@pytest.mark.parametrize(
    ('action', 'fought'),
    [
        # 타격은 싸움이다
        ({'harm': 'moderate'}, True),
        # 회복과 타격 없는 판정(설득)은 싸움이 아니다
        ({'recover': 'light'}, False),
        ({}, False),
    ],
)
def test_only_a_hit_on_an_npc_is_a_fight(action: dict, fought: bool):
    npc = TableNpc(entry_id=uuid.uuid4(), status=NpcStatus.ALIVE)
    judging = judging_with(npc)
    member = SimpleNamespace(user_id=ME)

    mark_npc_attack(judging, member, SimpleNamespace(**{'npc': npc.entry_id, 'harm': None, **action}))

    assert (npc.fought_round == 2) is fought
    assert (judging.fights.get(npc.entry_id) == {ME}) is fought


def test_a_dead_npc_is_not_fought():
    npc = TableNpc(entry_id=uuid.uuid4(), status=NpcStatus.DEAD)
    judging = judging_with(npc)

    mark_npc_attack(judging, SimpleNamespace(user_id=ME), SimpleNamespace(npc=npc.entry_id, harm='moderate'))

    assert (npc.fought_round, judging.fights) == (None, {})
