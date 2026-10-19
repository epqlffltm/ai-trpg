# game-server/tests/test_monster_drops.py

"""
몬스터를 쓰러뜨리면 엔진이 드롭을 주는 것(#372, app/rounds/drops.py)을 검증한다. 드롭은 지닌 것에서만 나온다(#456).
지닌 것을 따로 다루는 것은 test_monster_items.py 에 있다.

맵은 수로 입구(시작)와 깊은 수로다. 입구에 수로 쥐 둘(야수, 최대 HP 4), 깊은 수로에 해골 병사 하나(드롭 없음).
쥐의 소지품은 늑대 가죽 2개(100%)와 송곳니 1개(50%)다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.
눈은 판정, 피해의 양, 확률이 100 이 아닌 드롭 줄(백면체), 받을 사람이 둘 이상이면 고르는 눈의 차례다.

보는 것.
  - 시나리오: 드롭을 적고 읽는다. 개수와 확률의 범위, 같은 물건 두 줄, 줄 수의 상한. 게시할 때 물건 항목인지 본다.
    판에 굳고, 옛 판은 드롭이 없는 것으로 읽는다.
  - 라운드: 처음 쓰러뜨렸을 때 한 번만 준다(제압한 뒤 죽여도, 서술을 다시 맡겨도 다시 주지 않는다).
    그 장소의 죽지 않은 캐릭터 중 한 명이 받는다. 상한을 넘은 몫은 잃고 라운드는 닫힌다.
  - 이벤트: items_gained 에 출처와 잃은 개수가 붙고, 그 마리가 쓰러진 변화에 잇는다. 행한 사람이 없다.
  - 서술: 얻은 물건의 줄이 판정 줄에 붙는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CARRIED_MAX_INVENTORY, DROP_CHANCE_MAX, ITEM_STACK_MAX
from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_28
from app.engine.dice import ScriptedDice
from app.engine.drops import Dropped, comes_out
from app.rounds import records
from app.rounds.drops import hand_out, heirs
from app.rounds.llm_narrator import NarrationError
from app.rounds.move_lines import describe_drop
from app.rounds.narration_request import to_drop
from app.rounds.narrator import DropNote, DroppedNote, NarrationRequest, Preview
from app.tables.models import NpcStatus, TableItem, TableSheet
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.test_monster_combat import (
    BESTIARIES_URL,
    BITE_BACK,
    FAIL,
    LOREBOOKS_URL,
    PASS,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    declare,
    events_of,
    load_dice,
    monster_named,
    state_of,
    strike,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
RAT_SHEET = make_sheet(max_hp=4)
SKELETON_SHEET = make_sheet(max_hp=6)
# 송곳니가 나오는 눈과 안 나오는 눈(확률 50)
TOOTH = 50
NO_TOOTH = 51
# 쥐를 쓰러뜨리는 피해의 눈(보통 1d8, 쥐의 HP 4)
DOWN = 8


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def drop(entry: dict, count: int = 1, chance: int = 100) -> dict:
    return {'entry_id': entry['id'], 'count': count, 'chance': chance}


async def make_world(client: AsyncClient, me: dict[str, str]) -> dict:
    """로어북(장소 둘, 물건 둘, 인물 하나), 도감(쥐, 해골), 룰북. 시나리오는 아직 없다."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, entries, me, name='수로 입구', kind='place'),
        'deep': await post(client, entries, me, name='깊은 수로', kind='place'),
        'pelt': await post(client, entries, me, name='늑대 가죽', kind='item'),
        'tooth': await post(client, entries, me, name='송곳니', kind='item'),
        'keeper': await post(client, entries, me, name='수로지기', kind='person'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast', content='개만 한 쥐'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead', content='녹슨 창'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def rat_drops(world: dict) -> list[dict]:
    """쥐의 소지품. 늑대 가죽 2개(늘 떨어짐), 송곳니 1개(반)."""
    return [drop(world['pelt'], 2), drop(world['tooth'], 1, 50)]


async def make_scenario(client: AsyncClient, me: dict[str, str], world: dict, drops: list[dict], **fields) -> dict:
    """쥐가 drops 를 소지품으로 지닌 시나리오. 해골은 아무것도 지니지 않았다."""
    return await post(
        client,
        SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=world['rulebook']['id'],
        lorebook_ids=[world['lorebook']['id']],
        bestiary_ids=[world['bestiary']['id']],
        openings=['물 떨어지는 소리가 난다.'],
        default_sheet=SHEET,
        default_npc_sheet=SHEET,
        monster_sheets=[
            {'monster_id': world['rat']['id'], 'sheet': RAT_SHEET, 'inventory': drops},
            {'monster_id': world['skeleton']['id'], 'sheet': SKELETON_SHEET},
        ],
        start_place=world['gate']['id'],
        routes=[{'from_place': world['gate']['id'], 'to_place': world['deep']['id']}],
        encounters=[
            {'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 2},
            {'place_id': world['deep']['id'], 'monster_id': world['skeleton']['id'], 'count': 1},
        ],
        **fields,
    )


async def publish(client: AsyncClient, me: dict[str, str], scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def open_table(client: AsyncClient, me: dict[str, str], world: dict, *others: dict[str, str], **fields) -> dict:
    """쥐에 드롭이 있는 시나리오로 테이블을 시작한다. 모두 수로 입구에 선다. fields 는 시나리오에 더한다."""
    scenario = await make_scenario(client, me, world, rat_drops(world), **fields)
    assert (await publish(client, me, scenario)).status_code == status.HTTP_201_CREATED
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': table}


async def start_table(client: AsyncClient, me: dict[str, str], *others: dict[str, str]) -> dict:
    """새 로어북과 도감으로 open_table 을 한다."""
    return await open_table(client, me, await make_world(client, me), *others)


async def count_of(session: AsyncSession, table: dict, user_id: uuid.UUID, entry: dict) -> int:
    """그 사람의 지금 캐릭터가 가진 그 물건의 개수. DB 에서 읽는다."""
    sheets = select(TableSheet.id).where(TableSheet.table_id == uuid.UUID(table['id']), TableSheet.user_id == user_id)
    query = select(TableItem.count).where(TableItem.sheet_id.in_(sheets), TableItem.entry_id == uuid.UUID(entry['id']))
    return await session.scalar(query.execution_options(populate_existing=True)) or 0


async def kill_first_rat(client: AsyncClient, app: FastAPI, me: dict[str, str], world: dict, rolls: list[int]):
    """수로 쥐 1 을 제압해 쓰러뜨린다. 닫는 응답과 쥐, 주사위를 돌려준다."""
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    dice = load_dice(app, rolls)
    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))
    return closing, rat, dice


class FailingNarrator:
    """늘 잘려서 실패하는 서술자."""

    async def narrate(self, request: NarrationRequest, preview: Preview | None = None) -> str:
        raise NarrationError('cut_off')


# --- 시나리오 ---


async def test_drops_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, rat_drops(world))

    response = await publish(client, me, scenario)

    sheet = next(sheet for sheet in scenario['monster_sheets'] if sheet['monster_id'] == world['rat']['id'])
    assert (sheet['equipment'], sheet['inventory']) == ([], rat_drops(world))
    snapshot = read_snapshot(response.json()['snapshot'])
    rat = next(monster for monster in snapshot.monsters if monster.id == uuid.UUID(world['rat']['id']))
    skeleton = next(monster for monster in snapshot.monsters if monster.id == uuid.UUID(world['skeleton']['id']))
    assert [(str(line.entry_id), line.count, line.chance) for line in rat.inventory] == [
        (world['pelt']['id'], 2, 100),
        (world['tooth']['id'], 1, 50),
    ]
    assert (skeleton.equipment, skeleton.inventory) == ([], [])


@pytest.mark.parametrize(
    ('count', 'chance'),
    [(0, 50), (ITEM_STACK_MAX + 1, 50), (1, 0), (1, DROP_CHANCE_MAX + 1)],
)
async def test_count_and_chance_have_ranges(client: AsyncClient, me: dict[str, str], count: int, chance: int):
    world = await make_world(client, me)
    body = {
        'monster_sheets': [
            {'monster_id': world['rat']['id'], 'sheet': RAT_SHEET, 'inventory': [drop(world['pelt'], count, chance)]}
        ]
    }

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, {'title': '수로', **body}), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_same_item_twice_is_refused(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    drops = [drop(world['pelt'], 1), drop(world['pelt'], 2, 30)]
    body = {
        'title': '수로',
        'monster_sheets': [{'monster_id': world['rat']['id'], 'sheet': RAT_SHEET, 'inventory': drops}],
    }

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_monster_has_at_most_ten_inventory_lines(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    entries = f'{LOREBOOKS_URL}/{world["lorebook"]["id"]}/entries'
    things = [await post(client, entries, me, name=f'조각 {n}', kind='item') for n in range(CARRIED_MAX_INVENTORY + 1)]
    drops = [drop(thing) for thing in things]
    body = {
        'title': '수로',
        'monster_sheets': [{'monster_id': world['rat']['id'], 'sheet': RAT_SHEET, 'inventory': drops}],
    }

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(('pointed', 'problem'), [('keeper', 'item_not_item'), ('gone', 'item_entry_missing')])
async def test_a_drop_must_be_an_item_of_the_lorebooks(
    client: AsyncClient, me: dict[str, str], pointed: str, problem: str
):
    world = await make_world(client, me)
    entry = world[pointed] if pointed in world else {'id': str(uuid.uuid4())}
    scenario = await make_scenario(client, me, world, [drop(entry)])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_as_no_drops():
    document = {'format': 28, 'monsters': [{'id': str(uuid.uuid4()), 'name': '쥐', 'attacks': []}]}

    upgraded = upgrade_from_28(document)

    assert upgraded['format'] == 29
    assert upgraded['monsters'][0]['drops'] == []
    # 받은 문서는 고치지 않는다
    assert 'drops' not in document['monsters'][0]


# --- 라운드 ---


async def test_downing_a_monster_gives_its_drops(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)

    closing, rat, dice = await kill_first_rat(client, app, me, world, [PASS, DOWN, TOOTH])

    dropped = closing['declarations'][0]['outcome']['drop']
    assert dropped == {
        'source': 'monster',
        'monster_id': rat['id'],
        'monster_name': '수로 쥐 1',
        'npc_id': None,
        'npc_name': None,
        'user_id': str(ME),
        'character_name': '엘프',
        'items': [
            {'entry_id': world['pelt']['id'], 'name': '늑대 가죽', 'count': 2, 'lost': 0, 'total': 2},
            {'entry_id': world['tooth']['id'], 'name': '송곳니', 'count': 1, 'lost': 0, 'total': 1},
        ],
    }
    assert await state_of(session, rat['id']) == (0, NpcStatus.DOWNED)
    assert await count_of(session, world['table'], ME, world['pelt']) == 2
    assert await count_of(session, world['table'], ME, world['tooth']) == 1
    assert dice.remaining == 0


async def test_each_line_is_rolled_on_its_own(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)

    closing, _, _ = await kill_first_rat(client, app, me, world, [PASS, DOWN, NO_TOOTH])

    names = [item['name'] for item in closing['declarations'][0]['outcome']['drop']['items']]
    assert names == ['늑대 가죽']
    assert await count_of(session, world['table'], ME, world['tooth']) == 0


async def test_a_failed_check_drops_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)

    closing, _, dice = await kill_first_rat(client, app, me, world, [FAIL])

    assert closing['declarations'][0]['outcome']['drop'] is None
    assert dice.remaining == 0


async def test_a_wound_that_does_not_down_drops_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)

    # 피해 3 이면 HP 4 중 1 이 남는다. 쓰러지지 않았으니 굴리지 않는다
    closing, _, dice = await kill_first_rat(client, app, me, world, [PASS, 3])

    assert closing['declarations'][0]['outcome']['drop'] is None
    assert dice.remaining == 0


async def test_killing_a_downed_monster_does_not_drop_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    _, rat, _ = await kill_first_rat(client, app, me, world, [PASS, DOWN, TOOTH])
    await narrated()

    # 쓰러진 쥐를 죽인다. 판정과 피해의 눈만 있다. 드롭을 다시 굴리면 눈이 모자라 실패한다
    dice = load_dice(app, [PASS, DOWN])
    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id'], lethal=True))

    outcome = closing['declarations'][0]['outcome']
    assert outcome['monster_effect']['status'] == 'dead'
    assert outcome['drop'] is None
    assert dice.remaining == 0
    assert await count_of(session, world['table'], ME, world['pelt']) == 2


async def test_retrying_the_narration_does_not_drop_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    narrator = app.state.narrator
    app.state.narrator = FailingNarrator()
    await kill_first_rat(client, app, me, world, [PASS, DOWN, TOOTH])
    await narrated()

    # 서술만 다시 맡긴다. 판정은 닫기 시작할 때 한 번이었다
    app.state.narrator = narrator
    retried = await client.post(table_url(world['table'], '/rounds/current/close'), headers=me)
    await narrated()

    assert retried.status_code == status.HTTP_202_ACCEPTED, retried.text
    assert await count_of(session, world['table'], ME, world['pelt']) == 2
    assert len(await events_of(client, me, world['table'], 'items_gained')) == 2


async def test_the_receiver_is_one_of_those_standing_there(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    # 친구는 선언하지 않는다. 둘 다 입구에 있다. 고르는 눈 2 는 앉은 순서로 둘째, 친구다
    load_dice(app, [PASS, DOWN, NO_TOOTH, 2])
    await declare(client, friend, world['table'], '지켜본다.')

    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    outcomes = {declaration['character_name']: declaration['outcome'] for declaration in closing['declarations']}
    assert outcomes['엘프']['drop']['character_name'] == '드워프 기사'
    assert await count_of(session, world['table'], FRIEND, world['pelt']) == 2
    assert await count_of(session, world['table'], ME, world['pelt']) == 0


async def test_someone_elsewhere_does_not_receive(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await session.execute(
        text('UPDATE table_sheets SET place_id = :place WHERE table_id = :table AND user_id = :user'),
        {'place': world['deep']['id'], 'table': world['table']['id'], 'user': str(FRIEND)},
    )
    await session.commit()
    await declare(client, friend, world['table'], '지켜본다.')

    # 받을 사람이 나 하나라 고르는 눈이 없다
    closing, _, dice = await kill_first_rat(client, app, me, world, [PASS, DOWN, NO_TOOTH])

    outcomes = {declaration['character_name']: declaration['outcome'] for declaration in closing['declarations']}
    assert outcomes['엘프']['drop']['character_name'] == '엘프'
    assert dice.remaining == 0


async def test_a_full_stack_loses_the_overflow_and_the_round_closes(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    made = await make_world(client, me)
    full = {'entry_id': made['pelt']['id'], 'count': ITEM_STACK_MAX - 1}
    world = await open_table(client, me, made, starting_items=[full])

    closing, _, _ = await kill_first_rat(client, app, me, world, [PASS, DOWN, NO_TOOTH])
    await narrated()

    pelt = closing['declarations'][0]['outcome']['drop']['items'][0]
    assert (pelt['count'], pelt['lost'], pelt['total']) == (1, 1, ITEM_STACK_MAX)
    assert await count_of(session, world['table'], ME, world['pelt']) == ITEM_STACK_MAX
    current = await client.get(table_url(world['table'], '/rounds/current'), headers=me)
    assert current.json()['number'] == 2


# --- 이벤트와 서술 ---


async def test_the_gain_is_recorded_after_the_monster_falls(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    _, rat, _ = await kill_first_rat(client, app, me, world, [PASS, DOWN, NO_TOOTH])

    (gained,) = await events_of(client, me, world['table'], 'items_gained')
    (changed,) = await events_of(client, me, world['table'], 'monster_changed')

    assert gained['actor_id'] is None
    assert gained['caused_by_sequence'] == changed['sequence']
    assert gained['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'entry_id': world['pelt']['id'],
        'name': '늑대 가죽',
        'count': 2,
        'total': 2,
        'lost': 0,
        'source': 'monster',
        'monster_id': rat['id'],
        'monster_name': '수로 쥐 1',
    }


async def test_the_narration_is_told_what_was_gained(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    await kill_first_rat(client, app, me, world, [PASS, DOWN, TOOTH])
    await narrated()

    narrations = await events_of(client, me, world['table'], 'gm_narration')

    # 가짜 서술자는 한 일의 줄을 그대로 장면으로 내보낸다
    assert '(얻은 물건: 늑대 가죽 2개, 송곳니 → 엘프)' in narrations[-1]['payload']['text']


# --- DB 를 쓰지 않는 작은 함수들 ---


def test_a_sure_line_is_not_rolled():
    assert comes_out(100, ScriptedDice([])) is True


@pytest.mark.parametrize(('roll', 'expected'), [(1, True), (30, True), (31, False), (100, False)])
def test_a_line_comes_out_at_or_under_its_chance(roll: int, expected: bool):
    assert comes_out(30, ScriptedDice([roll])) is expected


def person(place: uuid.UUID | None, dead: bool = False) -> SimpleNamespace:
    """heirs 가 보는 만큼만 갖춘 앉은 사람."""
    sheet = SimpleNamespace(place_id=place, died_at='then' if dead else None, hp=5)
    return SimpleNamespace(sheet=sheet, user_id=uuid.uuid4(), character_name='누구')


def test_heirs_are_the_living_at_that_place():
    here, there = uuid.uuid4(), uuid.uuid4()
    alive, dead, away, unseated = person(here), person(here, dead=True), person(there), SimpleNamespace(sheet=None)
    table = SimpleNamespace(members=[alive, dead, away, unseated])

    assert heirs(table, here) == [alive]


def test_with_no_one_there_the_drop_vanishes():
    pelt = uuid.uuid4()
    judging = SimpleNamespace(
        table=SimpleNamespace(id=uuid.uuid4(), members=[]),
        items={pelt: SimpleNamespace(name='늑대 가죽')},
        dice=ScriptedDice([]),
    )
    monster = SimpleNamespace(state=SimpleNamespace(id=uuid.uuid4(), place_id=uuid.uuid4()), name='수로 쥐 1')

    dropped = hand_out(judging, monster, [Dropped(entry_id=pelt, count=2)])

    assert (dropped['user_id'], dropped['character_name']) == (None, None)
    assert dropped['items'] == [{'entry_id': str(pelt), 'name': '늑대 가죽', 'count': 0, 'lost': 2, 'total': None}]
    # 아무도 얻지 않았다. 서술자에게 주지 않는다
    assert to_drop(dropped) is None


@pytest.mark.parametrize(
    ('items', 'line'),
    [
        ([DroppedNote('늑대 가죽', 2), DroppedNote('송곳니', 1)], '(얻은 물건: 늑대 가죽 2개, 송곳니 → 엘프)'),
        ([DroppedNote('치유 물약', 1, lost=1)], '(얻은 물건: 치유 물약 → 엘프. 치유 물약 1개는 더 들 수 없어 잃었다)'),
        ([DroppedNote('치유 물약', 0, lost=2)], '(얻을 물건: 치유 물약 2개 → 엘프. 더 들 수 없어 모두 잃었다)'),
    ],
)
def test_the_drop_line(items: list[DroppedNote], line: str):
    assert describe_drop(DropNote(holder='수로 쥐 1', receiver='엘프', items=items)) == line


def test_a_vanished_drop_is_not_recorded(monkeypatch: pytest.MonkeyPatch):
    recorded = []
    monkeypatch.setattr(records.recorder, 'record', lambda *args, **kwargs: recorded.append(kwargs))
    lost = {'entry_id': 'p', 'name': '늑대 가죽', 'count': 0, 'lost': 2, 'total': None}
    vanished = {
        'source': 'monster',
        'monster_id': 'm',
        'monster_name': '수로 쥐 1',
        'user_id': None,
        'character_name': None,
        'items': [lost],
    }

    records.record_drop(None, None, vanished, cause=SimpleNamespace(payload={'round': 1}))
    records.record_drop(None, None, None, cause=SimpleNamespace(payload={'round': 1}))

    # 아무도 얻지 않았다. items_gained 를 남기지 않는다
    assert recorded == []
