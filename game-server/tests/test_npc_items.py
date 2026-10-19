# game-server/tests/test_npc_items.py

"""
NPC 가 지닌 물건과 처음 쓰러질 때의 드롭(#457 의 1/2)을 검증한다.

판은 test_npc_actions.py 의 것과 비슷하다. 스타팅에 악역영애(진짜 이름은 비올레타)가 나온다. 맵이 없다.
악역영애의 NPC 시트는 부채(레어) 하나를 장비로, 금화 5개(떨어질 확률 50)를 소지품으로 지녔다. 드워프는 시트가 없다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정, 피해의 양, 부상 표, 확률이 100 이 아닌 드롭 줄의 차례다.

보는 것.
  - 시나리오: 지닌 물건과 둔한지를 적고 판에 굳힌다. 같은 물건 두 줄, 장비와 소지품에 함께, 줄 수의 상한은 거부한다.
    게시할 때 물건 항목인지 본다. 옛 판의 인물은 아무것도 지니지 않고 둔하지 않다(판 형식 38).
  - 장면: 인물 목록에 지닌 물건이 장비 다음 소지품의 차례로 실린다.
  - 드롭: 처음 쓰러뜨렸을 때 지닌 것에서만 나온다. 나오지 않은 줄은 그 인물이 그대로 지닌다.
    회복해 일어났다가 또 쓰러져도 다시 굴리지 않는다. 받는 곳은 친 사람이 선 장소다.
  - 이벤트와 서술: items_gained 의 출처가 npc 이고 그 인물이 쓰러진 변화에 잇는다. 얻은 물건의 줄이 서술에 간다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CARRIED_MAX_EQUIPMENT
from app.assets.scenarios.snapshot import CarriedItemSnapshot, NpcSheetSnapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_37
from app.engine.dice import ScriptedDice
from app.engine.drops import Dropped
from app.rounds.cast import CastMember
from app.rounds.drops import NPC_SOURCE, hand_out_npc, npc_drop_after
from app.rounds.narration_request import to_drop
from app.tables import npc_items
from app.tables.models import TableItem, TableNpc
from app.tables.npcs import mark_first_fall
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.test_npc_actions import (
    LOREBOOKS_URL,
    NO_INJURY,
    OPENING,
    PASS,
    PUNCH,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    TEND,
    bearer,
    declare,
    events_of,
    load_dice,
    people,
    post,
    punch,
    table_url,
    tend,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
LADY_SHEET = make_sheet(max_hp=10)
# 금화가 떨어지는 눈과 안 떨어지는 눈(확률 50)
COINS = 50
NO_COINS = 51
# 악역영애(최대 HP 10)를 쓰러뜨리는 큰 피해(2d8)의 눈
DOWN = [8, 8]


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def make_lore(client: AsyncClient, me: dict) -> dict:
    """인물 둘(악역영애, 드워프), 물건 둘(부채, 금화), 장소 하나가 든 로어북과 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    return {
        'lorebook': lorebook,
        'lady': await post(
            client, entries, me, name='비올레타', keywords=['악역영애'], content='끄나풀', kind='person'
        ),
        'dwarf': await post(client, entries, me, name='드워프', keywords=['망치'], content='추격자', kind='person'),
        'fan': await post(client, entries, me, name='부채', kind='item'),
        'coins': await post(client, entries, me, name='금화', kind='item'),
        'highway': await post(client, entries, me, name='우주 고속도로', kind='place'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def lady_sheet(lore: dict, **fields) -> dict:
    """악역영애의 시트. 부채를 장비로, 금화 5개(반)를 소지품으로 지닌다. fields 로 칸을 바꾼다."""
    sheet = {
        'entry_id': lore['lady']['id'],
        'sheet': LADY_SHEET,
        'equipment': [{'entry_id': lore['fan']['id']}],
        'inventory': [{'entry_id': lore['coins']['id'], 'count': 5, 'chance': 50}],
    }
    return {**sheet, **fields}


async def make_scenario(client: AsyncClient, me: dict, lore: dict, sheet: dict) -> dict:
    return await post(
        client,
        SCENARIOS_URL,
        me,
        title='열일곱 행성 추격전',
        rulebook_id=lore['rulebook']['id'],
        lorebook_ids=[lore['lorebook']['id']],
        openings=[OPENING],
        default_sheet=SHEET,
        items=[{'entry_id': lore['fan']['id'], 'rarity': 'rare'}],
        npc_sheets=[sheet],
        default_npc_sheet=make_sheet(max_hp=6),
    )


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict) -> dict:
    """악역영애가 부채와 금화를 지닌 시나리오로 테이블을 시작한다. 나 혼자 앉는다."""
    lore = await make_lore(client, me)
    scenario = await make_scenario(client, me, lore, lady_sheet(lore))
    published = await publish(client, me, scenario)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**lore, 'table': table}


async def knock_down(client: AsyncClient, app: FastAPI, me: dict, world: dict, rolls: list[int]):
    """악역영애를 제압해 쓰러뜨린다. 닫는 응답의 첫 선언의 결과와 주사위를 돌려준다."""
    dice = load_dice(app, [PASS, *DOWN, NO_INJURY, *rolls])
    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy'))
    return closing['declarations'][0]['outcome'], dice


async def carried_by_lady(client: AsyncClient, me: dict, world: dict) -> list[tuple[str, int]]:
    (lady,) = (await people(client, me, world['table']))['people']
    return [(thing['name'], thing['count']) for thing in lady['items']]


async def count_of(session: AsyncSession, world: dict, entry: dict) -> int:
    query = select(TableItem.count).where(
        TableItem.table_id == uuid.UUID(world['table']['id']), TableItem.entry_id == uuid.UUID(entry['id'])
    )
    return await session.scalar(query.execution_options(populate_existing=True)) or 0


# --- 시나리오 ---


async def test_carried_items_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    lore = await make_lore(client, me)
    scenario = await make_scenario(client, me, lore, lady_sheet(lore, dull=True))

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    (saved,) = scenario['npc_sheets']
    assert saved['equipment'] == [{'entry_id': lore['fan']['id'], 'count': 1, 'chance': 100}]
    assert saved['dull'] is True
    (lady,) = read_snapshot(response.json()['snapshot']).npc_sheets
    assert [(str(line.entry_id), line.count, line.chance) for line in lady.inventory] == [(lore['coins']['id'], 5, 50)]
    assert lady.dull is True


@pytest.mark.parametrize(
    'change',
    [
        # 같은 물건이 한 목록에 두 줄
        lambda lore: {'inventory': [{'entry_id': lore['coins']['id']}, {'entry_id': lore['coins']['id']}]},
        # 같은 물건이 장비와 소지품에 함께
        lambda lore: {'inventory': [{'entry_id': lore['fan']['id']}]},
        # 장비의 줄 수가 상한을 넘는다
        lambda lore: {'equipment': [{'entry_id': str(uuid.uuid4())} for _ in range(CARRIED_MAX_EQUIPMENT + 1)]},
    ],
)
async def test_badly_carried_items_are_refused(client: AsyncClient, me: dict[str, str], change):
    lore = await make_lore(client, me)
    body = {'title': '추격전', 'npc_sheets': [lady_sheet(lore, **change(lore))]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(('pointed', 'problem'), [('dwarf', 'item_not_item'), ('gone', 'item_entry_missing')])
async def test_a_carried_line_must_be_an_item_of_the_lorebooks(
    client: AsyncClient, me: dict[str, str], pointed: str, problem: str
):
    lore = await make_lore(client, me)
    entry = lore[pointed] if pointed in lore else {'id': str(uuid.uuid4())}
    scenario = await make_scenario(client, me, lore, lady_sheet(lore, inventory=[{'entry_id': entry['id']}]))

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_everyone_as_carrying_nothing():
    sheet = {'entry_id': str(uuid.uuid4()), 'sheet': SHEET, 'attitude': 'neutral'}
    document = {'format': 37, 'npc_sheets': [sheet]}

    upgraded = upgrade_from_37(document)

    assert upgraded['format'] == 38
    assert upgraded['npc_sheets'] == [{**sheet, 'equipment': [], 'inventory': [], 'dull': False}]
    assert 'equipment' not in document['npc_sheets'][0]
    assert UPGRADES[37] is upgrade_from_37


# --- 장면 ---


async def test_the_people_list_shows_what_the_person_carries(client: AsyncClient, me: dict[str, str]):
    world = await start(client, me)

    (lady,) = (await people(client, me, world['table']))['people']

    assert lady['items'] == [
        {'entry_id': world['fan']['id'], 'name': '부채', 'rarity': 'rare', 'count': 1, 'equipped': True},
        {'entry_id': world['coins']['id'], 'name': '금화', 'rarity': 'normal', 'count': 5, 'equipped': False},
    ]


# --- 드롭 ---


async def test_downing_an_npc_gives_what_falls_and_the_rest_stays(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start(client, me)

    outcome, dice = await knock_down(client, app, me, world, [NO_COINS])
    await narrated()

    assert outcome['npc_effect']['status'] == 'downed'
    assert outcome['drop'] == {
        'source': 'npc',
        'monster_id': None,
        'monster_name': None,
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
        'user_id': str(ME),
        'character_name': '엘프',
        'items': [{'entry_id': world['fan']['id'], 'name': '부채', 'count': 1, 'lost': 0, 'total': 1}],
    }
    assert dice.remaining == 0
    assert await count_of(session, world, world['fan']) == 1
    # 떨어지지 않은 금화는 악역영애가 그대로 지닌다(#475 의 빼앗기로 가져간다)
    assert await carried_by_lady(client, me, world) == [('금화', 5)]


async def test_a_downed_npc_drops_only_the_first_time(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start(client, me)
    await knock_down(client, app, me, world, [NO_COINS])
    await narrated()
    load_dice(app, [PASS, 2])
    await declare(client, me, world['table'], TEND, tend(world['lady']['id']))
    await narrated()

    # 일어났다가 또 쓰러진다. 금화의 줄을 다시 굴리지 않는다(남긴 눈을 쓰지 않는다)
    outcome, dice = await knock_down(client, app, me, world, [COINS])

    assert outcome['npc_effect']['status'] == 'downed'
    assert outcome['drop'] is None
    assert dice.remaining == 1
    npc = await session.scalar(
        select(TableNpc)
        .where(TableNpc.entry_id == uuid.UUID(world['lady']['id']))
        .execution_options(populate_existing=True)
    )
    assert npc.fell_round == 1


async def test_the_first_fall_is_written_and_the_fallen_line_is_emptied(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start(client, me)
    # 부채(장비, 줄 0)는 늘 떨어지고 금화(소지품, 줄 1)는 떨어지지 않는다
    outcome, _ = await knock_down(client, app, me, world, [NO_COINS])

    assert [thing['name'] for thing in outcome['drop']['items']] == ['부채']
    npc = await session.scalar(
        select(TableNpc)
        .where(TableNpc.entry_id == uuid.UUID(world['lady']['id']))
        .execution_options(populate_existing=True)
    )
    assert (npc.fell_round, [(row.slot, row.count) for row in npc.items]) == (1, [(0, 0)])


# --- 이벤트와 서술 ---


async def test_the_gain_is_recorded_after_the_npc_falls(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start(client, me)
    await knock_down(client, app, me, world, [NO_COINS])

    (gained,) = await events_of(client, me, world['table'], 'items_gained')
    (changed,) = await events_of(client, me, world['table'], 'npc_changed')

    assert gained['actor_id'] is None
    assert gained['caused_by_sequence'] == changed['sequence']
    assert gained['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'entry_id': world['fan']['id'],
        'name': '부채',
        'count': 1,
        'total': 1,
        'lost': 0,
        'source': 'npc',
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
    }


async def test_the_narration_is_told_what_was_gained(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start(client, me)
    await knock_down(client, app, me, world, [COINS])
    await narrated()

    narrations = await events_of(client, me, world['table'], 'gm_narration')

    assert '(얻은 물건: 부채, 금화 5개 → 엘프)' in narrations[-1]['payload']['text']


# --- DB 를 쓰지 않는 작은 함수들 ---


def member_at(place: uuid.UUID) -> SimpleNamespace:
    """드롭을 받을 수 있는 앉은 사람. 그 장소에 살아 있다."""
    sheet = SimpleNamespace(id=uuid.uuid4(), place_id=place, died_at=None, hp=5, items=[])
    return SimpleNamespace(sheet=sheet, user_id=uuid.uuid4(), character_name='누구')


def test_an_npc_drop_goes_to_someone_at_the_hitters_place():
    here, there = uuid.uuid4(), uuid.uuid4()
    near, far = member_at(here), member_at(there)
    judging = SimpleNamespace(
        table=SimpleNamespace(id=uuid.uuid4(), members=[far, near]),
        items={},
        dice=ScriptedDice([]),
    )
    person = SimpleNamespace(entry_id=uuid.uuid4(), name='악역영애')

    dropped = hand_out_npc(judging, there, person, [])

    assert (dropped['source'], dropped['npc_id'], dropped['npc_name']) == (NPC_SOURCE, str(person.entry_id), '악역영애')
    assert dropped['user_id'] == str(far.user_id)


def test_an_npc_drop_falls_from_what_it_carries_to_the_hitters_place():
    here, there = uuid.uuid4(), uuid.uuid4()
    near, hitter = member_at(here), member_at(there)
    fan = CarriedItemSnapshot(entry_id=uuid.uuid4(), count=1, chance=100)
    definition = NpcSheetSnapshot(entry_id=uuid.uuid4(), sheet=SHEET, equipment=[fan])
    npc = TableNpc(table_id=uuid.uuid4(), entry_id=definition.entry_id)
    npc.items = []
    judging = SimpleNamespace(
        table=SimpleNamespace(id=npc.table_id, members=[near, hitter]),
        items={fan.entry_id: SimpleNamespace(name='부채')},
        dice=ScriptedDice([]),
        cast=[CastMember(definition.entry_id, '악역영애', npc, definition)],
        round_number=4,
    )
    effect = {'entry_id': str(definition.entry_id), 'status_before': 'alive', 'status': 'downed'}

    dropped = npc_drop_after(judging, hitter, effect)

    # 친 사람이 선 장소(there)에는 친 사람뿐이다. 고르는 눈을 굴리지 않는다
    assert dropped['user_id'] == str(hitter.user_id)
    assert (npc.fell_round, [(row.slot, row.count) for row in npc.items]) == (4, [(0, 0)])


def test_with_no_one_there_an_npc_drop_vanishes():
    coins = uuid.uuid4()
    judging = SimpleNamespace(
        table=SimpleNamespace(id=uuid.uuid4(), members=[]),
        items={coins: SimpleNamespace(name='금화')},
        dice=ScriptedDice([]),
    )
    person = SimpleNamespace(entry_id=uuid.uuid4(), name='악역영애')

    dropped = hand_out_npc(judging, uuid.uuid4(), person, [Dropped(entry_id=coins, count=5)])

    assert dropped['user_id'] is None
    assert dropped['items'] == [{'entry_id': str(coins), 'name': '금화', 'count': 0, 'lost': 5, 'total': None}]
    assert to_drop(dropped) is None


def test_the_narrator_hears_the_npcs_name_as_the_holder():
    drop = {
        'source': NPC_SOURCE,
        'npc_id': str(uuid.uuid4()),
        'npc_name': '악역영애',
        'user_id': str(ME),
        'character_name': '엘프',
        'items': [{'entry_id': str(uuid.uuid4()), 'name': '부채', 'count': 1, 'lost': 0, 'total': 1}],
    }

    assert (to_drop(drop).holder, to_drop(drop).receiver) == ('악역영애', '엘프')


def test_only_the_first_fall_is_marked():
    npc = TableNpc(entry_id=uuid.uuid4())

    assert mark_first_fall(npc, 3) is True
    assert mark_first_fall(npc, 5) is False
    assert npc.fell_round == 3


def test_a_person_without_a_sheet_carries_nothing():
    npc = TableNpc(table_id=uuid.uuid4(), entry_id=uuid.uuid4())
    npc.items = []

    assert npc_items.carried(npc, None) == []


def test_setting_a_count_makes_a_row_for_that_person():
    coins = CarriedItemSnapshot(entry_id=uuid.uuid4(), count=5, chance=50)
    definition = NpcSheetSnapshot(entry_id=uuid.uuid4(), sheet=SHEET, inventory=[coins])
    npc = TableNpc(table_id=uuid.uuid4(), entry_id=definition.entry_id)
    npc.items = []

    npc_items.set_count(npc, 0, 2)
    npc_items.set_count(npc, 0, 1)

    assert [(row.table_id, row.entry_id, row.slot, row.count) for row in npc.items] == [
        (npc.table_id, npc.entry_id, 0, 1)
    ]
    (held,) = npc_items.carried(npc, definition)
    assert (held.entry_id, held.count, held.equipped, held.chance) == (coins.entry_id, 1, False, 50)
