# game-server/tests/test_monster_items.py

"""
몬스터가 지닌 물건(장비와 소지품, #456, app/tables/monster_items.py)을 검증한다.

맵과 판은 test_monster_drops.py 의 것이다. 수로 입구(시작)에 수로 쥐 둘, 깊은 수로에 해골 병사 하나.
여기서는 쥐가 송곳니 1개를 장비로(늘 떨어짐), 늑대 가죽 2개를 소지품으로(반) 지녔다.

보는 것.
  - 시나리오: 장비와 소지품을 적고 판에 굳힌다. 같은 물건을 두 곳에 적으면 거부, 장비는 5 줄까지.
    옛 판과 옛 시나리오의 드롭은 소지품으로 읽는다(판 형식 34, 마이그레이션 5d2c8e7a1f34).
  - 장면: 몬스터마다 지금 지닌 것이 장비 다음 소지품의 차례로 실린다.
  - 드롭: 지닌 것에서만 떨어진다. 떨어진 줄은 마리에게서 빠지고, 떨어지지 않은 줄은 그대로 지닌다.
    바뀐 줄만 적는다. 다른 마리는 그대로다.
"""

import importlib.util
import pathlib
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import MONSTER_MAX_EQUIPMENT
from app.assets.scenarios.snapshot import MonsterItemSnapshot, MonsterSnapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_33
from app.engine.dice import ScriptedDice
from app.rounds.drops import fall_from
from app.tables import monster_items
from app.tables.models import TableMonster, TableMonsterItem
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.test_monster_combat import (
    BITE_BACK,
    PASS,
    SCENARIOS_URL,
    TABLES_URL,
    declare,
    load_dice,
    monster_named,
    strike,
    table_url,
)
from tests.test_monster_drops import (
    DOWN,
    LOREBOOKS_URL,
    ME,
    RAT_SHEET,
    SKELETON_SHEET,
    bearer,
    drop,
    make_world,
    post,
    publish,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 늑대 가죽(확률 50)이 떨어지는 눈과 안 떨어지는 눈
PELT = 50
NO_PELT = 51
MIGRATION = pathlib.Path(__file__).parent.parent / 'migrations/versions/20261019_5d2c8e7a1f34_monster_items.py'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


def rat_sheet(world: dict, equipment: list[dict] | None = None, inventory: list[dict] | None = None) -> dict:
    """쥐의 시트. 기본은 송곳니 1개를 장비로, 늑대 가죽 2개를 소지품으로 지닌다."""
    return {
        'monster_id': world['rat']['id'],
        'sheet': RAT_SHEET,
        'equipment': [drop(world['tooth'])] if equipment is None else equipment,
        'inventory': [drop(world['pelt'], 2, 50)] if inventory is None else inventory,
    }


async def make_scenario(client: AsyncClient, me: dict[str, str], world: dict) -> dict:
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
        monster_sheets=[rat_sheet(world), {'monster_id': world['skeleton']['id'], 'sheet': SKELETON_SHEET}],
        start_place=world['gate']['id'],
        routes=[{'from_place': world['gate']['id'], 'to_place': world['deep']['id']}],
        encounters=[
            {'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 2},
            {'place_id': world['deep']['id'], 'monster_id': world['skeleton']['id'], 'count': 1},
        ],
    )


async def start_table(client: AsyncClient, me: dict[str, str]) -> dict:
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world)
    assert (await publish(client, me, scenario)).status_code == status.HTTP_201_CREATED
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': table}


def carried_names(monster: dict) -> list[tuple[str, int, bool]]:
    return [(item['name'], item['count'], item['equipped']) for item in monster['items']]


async def rows_of(session: AsyncSession, monster_id: str) -> list[tuple[int, int]]:
    """DB 에 적힌 그 마리의 바뀐 줄들(번호, 개수)."""
    query = select(TableMonsterItem).where(TableMonsterItem.monster_id == uuid.UUID(monster_id))
    rows = await session.scalars(query.order_by(TableMonsterItem.slot).execution_options(populate_existing=True))
    return [(row.slot, row.count) for row in rows]


# --- 시나리오 ---


async def test_carried_items_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    rat = next(monster for monster in read_snapshot(response.json()['snapshot']).monsters if monster.name == '수로 쥐')
    assert [(str(line.entry_id), line.count, line.chance) for line in rat.equipment] == [(world['tooth']['id'], 1, 100)]
    assert [(str(line.entry_id), line.count, line.chance) for line in rat.inventory] == [(world['pelt']['id'], 2, 50)]


async def test_count_and_chance_default_to_one_and_always(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    sheet = rat_sheet(world, equipment=[{'entry_id': world['tooth']['id']}], inventory=[])
    body = {'title': '수로', 'monster_sheets': [sheet]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    (saved,) = response.json()['monster_sheets']
    assert saved['equipment'] == [{'entry_id': world['tooth']['id'], 'count': 1, 'chance': 100}]


@pytest.mark.parametrize('case', ['both', 'too-much-equipment'])
async def test_bad_carried_items_are_refused(client: AsyncClient, me: dict[str, str], case: str):
    world = await make_world(client, me)
    if case == 'both':
        sheet = rat_sheet(world, equipment=[drop(world['pelt'])], inventory=[drop(world['pelt'], 2)])
    else:
        entries = f'{LOREBOOKS_URL}/{world["lorebook"]["id"]}/entries'
        things = [
            await post(client, entries, me, name=f'갑옷 {n}', kind='item') for n in range(MONSTER_MAX_EQUIPMENT + 1)
        ]
        sheet = rat_sheet(world, equipment=[drop(thing) for thing in things], inventory=[])
    body = {'title': '수로', 'monster_sheets': [sheet]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_drops_are_no_longer_written(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    sheet = {'monster_id': world['rat']['id'], 'sheet': RAT_SHEET, 'drops': [drop(world['pelt'])]}
    body = {'title': '수로', 'monster_sheets': [sheet]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_an_old_snapshot_reads_drops_as_inventory():
    line = {'entry_id': str(uuid.uuid4()), 'count': 2, 'chance': 50}
    document = {'format': 33, 'monsters': [{'id': 'm', 'drops': [line]}]}

    upgraded = upgrade_from_33(document)

    assert upgraded['format'] == 34
    assert upgraded['monsters'] == [{'id': 'm', 'equipment': [], 'inventory': [line]}]
    # 받은 문서는 고치지 않는다
    assert 'drops' in document['monsters'][0]


def test_the_migration_moves_drafted_drops_and_back():
    spec = importlib.util.spec_from_file_location('monster_items_migration', MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    line = {'entry_id': str(uuid.uuid4()), 'count': 2, 'chance': 50}
    drafted = {'monster_id': 'm', 'sheet': {}, 'attacks': [], 'drops': [line]}

    moved = migration.carried_from_drops(drafted)

    assert moved == {'monster_id': 'm', 'sheet': {}, 'attacks': [], 'equipment': [], 'inventory': [line]}
    assert migration.drops_from_carried(moved) == drafted


# --- 장면과 드롭 ---


async def test_the_scene_shows_what_each_monster_carries(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    rat = await monster_named(client, me, world['table'], '수로 쥐 2')

    assert carried_names(rat) == [('송곳니', 1, True), ('늑대 가죽', 2, False)]


async def test_what_does_not_fall_stays_with_the_monster(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, DOWN, NO_PELT])

    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    # 송곳니(장비, 늘)는 떨어져 엘프가 받았고, 가죽(반)은 떨어지지 않아 쓰러진 쥐가 그대로 지닌다
    dropped = closing['declarations'][0]['outcome']['drop']['items']
    assert [(item['name'], item['count']) for item in dropped] == [('송곳니', 1)]
    assert await rows_of(session, rat['id']) == [(0, 0)]
    other = await monster_named(client, me, world['table'], '수로 쥐 2')
    assert await rows_of(session, other['id']) == []
    downed = await monster_named(client, me, world['table'], '수로 쥐 1')
    assert carried_names(downed) == [('늑대 가죽', 2, False)]


async def test_all_that_falls_leaves_the_monster(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, DOWN, PELT])

    await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    assert await rows_of(session, rat['id']) == [(0, 0), (1, 0)]
    assert carried_names(await monster_named(client, me, world['table'], '수로 쥐 1')) == []


# --- DB 를 쓰지 않는 작은 함수들 ---


def definition(equipment: list[MonsterItemSnapshot], inventory: list[MonsterItemSnapshot]) -> MonsterSnapshot:
    return MonsterSnapshot.model_construct(equipment=equipment, inventory=inventory)


def line(count: int, chance: int = 100) -> MonsterItemSnapshot:
    return MonsterItemSnapshot(entry_id=uuid.uuid4(), count=count, chance=chance)


def test_untouched_lines_are_read_from_the_snapshot():
    sword, coins = line(1), line(30)
    monster = TableMonster(id=uuid.uuid4())
    monster.items = [TableMonsterItem(slot=1, count=12)]

    held = monster_items.carried(monster, definition([sword], [coins]))

    assert [(one.slot, one.entry_id, one.count, one.equipped) for one in held] == [
        (0, sword.entry_id, 1, True),
        (1, coins.entry_id, 12, False),
    ]


def test_an_emptied_line_is_not_carried():
    monster = TableMonster(id=uuid.uuid4())
    monster.items = [TableMonsterItem(slot=0, count=0)]

    assert monster_items.carried(monster, definition([line(1)], [])) == []


def test_set_count_adds_a_row_once():
    monster = TableMonster(id=uuid.uuid4())
    monster.items = []

    monster_items.set_count(monster, 2, 5)
    monster_items.set_count(monster, 2, 3)

    assert [(row.monster_id, row.slot, row.count) for row in monster.items] == [(monster.id, 2, 3)]


def test_falling_rolls_each_line_and_empties_what_fell():
    sure, maybe = line(1), line(4, chance=30)
    monster = TableMonster(id=uuid.uuid4())
    monster.items = []
    scene_monster = type('SceneMonster', (), {'state': monster, 'definition': definition([sure], [maybe])})
    judging = type('Judging', (), {'dice': ScriptedDice([31])})

    fallen = fall_from(scene_monster, judging)

    assert [(one.entry_id, one.count) for one in fallen] == [(sure.entry_id, 1)]
    assert [(row.slot, row.count) for row in monster.items] == [(0, 0)]
