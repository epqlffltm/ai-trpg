# game-server/tests/test_encounters.py

"""
조우와 테이블의 몬스터 상태(#231 2단계)를 검증한다.

넷을 본다.
  - 시나리오: 조우를 적고 읽고 고친다. 모양만 본다.
  - 게시: 조우가 붙인 로어북의 장소와 시트를 적은 몬스터를 가리키는지, 맵이 있는지.
  - 판: 형식 22 에 실린다. 옛 판은 조우 없이 읽는다. 판의 계약이 엉뚱한 조우를 거부한다.
  - 테이블: 시작할 때 조우마다 마리 수만큼 상태가 생겨 그 장소에 놓인다. 앉은 사람에게는 드러나지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ENCOUNTER_MAX_COUNT, SCENARIO_MAX_ENCOUNTERS
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_21
from app.main import API_PREFIX
from app.tables.models import NpcStatus, TableMonster
from tests.narration_model import asset_body, with_model
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

RAT_SHEET = make_sheet(dex=14, max_hp=4)
SKELETON_SHEET = make_sheet(str=13, max_hp=13)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
async def world(client: AsyncClient, me: dict[str, str]) -> dict:
    """장소 둘(수로 입구, 깊은 수로)과 인물 하나가 든 로어북, 몬스터 셋(쥐, 해골, 시트를 주지 않을 골렘)이 든 도감."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, entries, me, name='수로 입구', kind='place'),
        'deep': await post(client, entries, me, name='깊은 수로', kind='place'),
        'keeper': await post(client, entries, me, name='수문지기', kind='person'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead'),
        'golem': await post(client, monsters, me, name='돌 골렘', kind='construct'),
    }


def encounter(place: dict, monster: dict, count: int, surprise: str = 'none') -> dict:
    return {'place_id': place['id'], 'monster_id': monster['id'], 'count': count, 'surprise': surprise}


def with_map(world: dict, **fields) -> dict:
    """맵(수로 입구에서 시작, 깊은 수로로 가는 길)과 쥐, 해골의 시트를 둔 시나리오의 칸들."""
    body = {
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'monster_sheets': [
            {'monster_id': world['rat']['id'], 'sheet': RAT_SHEET},
            {'monster_id': world['skeleton']['id'], 'sheet': SKELETON_SHEET},
        ],
        'default_npc_sheet': SHEET,
        'start_place': world['gate']['id'],
        'routes': [{'from_place': world['gate']['id'], 'to_place': world['deep']['id']}],
    }
    body.update(fields)
    return body


async def create_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """룰북, 스타팅, 기본 시트가 있는 시나리오."""
    rulebook = await post(client, RULEBOOKS_URL, headers, title='룰북')
    body = {
        'title': '지하 수로',
        'rulebook_id': rulebook['id'],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
    }
    body.update(fields)
    return await post(client, SCENARIOS_URL, headers, **body)


async def try_publish(client: AsyncClient, headers: dict[str, str], scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)


async def refused(client: AsyncClient, headers: dict[str, str], scenario: dict) -> list[str]:
    """게시를 거절당한 이유들."""
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    return response.json()['problems']


async def published(client: AsyncClient, headers: dict[str, str], scenario: dict) -> dict:
    """게시한 판의 내용."""
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['snapshot']


async def start_table(client: AsyncClient, headers: dict[str, str], scenario: dict) -> dict:
    """혼자 앉아 기본 시트로 캐릭터를 정하고 시작한 테이블."""
    table = await post(client, TABLES_URL, headers, scenario_id=scenario['id'], version=1, capacity=1)
    character = await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '카이'}, headers=headers)
    assert character.status_code == status.HTTP_200_OK, character.text
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=headers)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def monsters_of(session: AsyncSession, table: dict) -> list[TableMonster]:
    """테이블의 몬스터 상태들. 만든 순서를 알 수 없으므로 몬스터, 번호의 순서로 놓는다."""
    query = (
        select(TableMonster)
        .where(TableMonster.table_id == uuid.UUID(table['id']))
        .order_by(TableMonster.monster_id, TableMonster.number)
    )
    return list(await session.scalars(query))


# --- 시나리오: 적고 읽고 고친다 ---


async def test_encounters_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [encounter(world['deep'], world['rat'], 3)]
    scenario = await create_scenario(client, me, **with_map(world, encounters=encounters))

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['encounters'] == encounters


async def test_a_scenario_starts_without_encounters(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me)

    assert scenario['encounters'] == []


@pytest.mark.parametrize(
    'encounters',
    [
        # 같은 장소의 같은 몬스터는 한 줄에 마리 수로 적는다
        [
            {'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': 1},
            {'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': 2},
        ],
        [{'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': 0}],
        [{'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': ENCOUNTER_MAX_COUNT + 1}],
        [{'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID}],
        [{'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': 1, 'hidden': True}],
        [
            {'place_id': str(uuid.uuid4()), 'monster_id': NO_SUCH_ID, 'count': 1}
            for _ in range(SCENARIO_MAX_ENCOUNTERS + 1)
        ],
    ],
)
async def test_rejects_bad_encounters(client: AsyncClient, me: dict[str, str], encounters: list):
    response = await client.post(
        SCENARIOS_URL, json=with_model({'title': '지하 수로', 'encounters': encounters}), headers=me
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_same_monster_may_be_in_two_places(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [encounter(world['gate'], world['rat'], 1), encounter(world['deep'], world['rat'], 2)]

    scenario = await create_scenario(client, me, **with_map(world, encounters=encounters))

    assert scenario['encounters'] == encounters


async def test_updating_replaces_or_keeps_the_encounters(client: AsyncClient, me: dict[str, str], world: dict):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['rat'], 3)])
    )
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    kept = await client.patch(url, json={'title': '새 제목'}, headers=me)
    changed = await client.patch(url, json={'encounters': [encounter(world['gate'], world['skeleton'], 1)]}, headers=me)
    cleared = await client.patch(url, json={'encounters': []}, headers=me)

    assert kept.json()['encounters'] == [encounter(world['deep'], world['rat'], 3)]
    assert changed.json()['encounters'] == [encounter(world['gate'], world['skeleton'], 1)]
    assert cleared.json()['encounters'] == []


# --- 게시 ---


async def test_encounters_are_frozen_into_the_version(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [encounter(world['deep'], world['rat'], 3), encounter(world['deep'], world['skeleton'], 1)]
    scenario = await create_scenario(client, me, **with_map(world, encounters=encounters))

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT
    assert snapshot['encounters'] == encounters


async def test_an_encounter_at_an_unattached_place_is_refused(client: AsyncClient, me: dict[str, str], world: dict):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter({'id': NO_SUCH_ID}, world['rat'], 1)])
    )

    assert await refused(client, me, scenario) == ['encounter_place_missing']


async def test_an_encounter_somewhere_that_is_not_a_place_is_refused(
    client: AsyncClient, me: dict[str, str], world: dict
):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['keeper'], world['rat'], 1)])
    )

    assert await refused(client, me, scenario) == ['encounter_not_place']


async def test_an_encounter_with_a_monster_without_a_sheet_is_refused(
    client: AsyncClient, me: dict[str, str], world: dict
):
    # 골렘은 도감에 있지만 시트가 없다. 이 시나리오가 쓰지 않는 몬스터라 숫자가 없다
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['golem'], 1)])
    )

    assert await refused(client, me, scenario) == ['encounter_monster_missing']


async def test_encounters_need_a_map(client: AsyncClient, me: dict[str, str], world: dict):
    fields = with_map(world, encounters=[encounter(world['deep'], world['rat'], 1)], start_place=None, routes=[])
    scenario = await create_scenario(client, me, **fields)

    assert await refused(client, me, scenario) == ['encounter_map_missing']


async def test_every_problem_of_the_encounters_is_told_at_once(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [
        encounter({'id': NO_SUCH_ID}, world['rat'], 1),
        encounter(world['keeper'], world['rat'], 1),
        encounter(world['deep'], world['golem'], 1),
    ]
    scenario = await create_scenario(client, me, **with_map(world, encounters=encounters))

    assert await refused(client, me, scenario) == [
        'encounter_place_missing',
        'encounter_not_place',
        'encounter_monster_missing',
    ]


# --- 판: 계약과 옛 판 ---


async def test_the_snapshot_refuses_encounters_that_point_at_nothing(
    client: AsyncClient, me: dict[str, str], world: dict
):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['rat'], 2)])
    )
    document = await published(client, me, scenario)

    # 게시가 막는 것을 판의 계약도 막는다. 테이블의 시작은 마리마다 숫자와 자리가 있다고 믿는다
    for broken in (
        [encounter({'id': NO_SUCH_ID}, world['rat'], 1)],
        [encounter(world['keeper'], world['rat'], 1)],
        [encounter(world['deep'], world['golem'], 1)],
    ):
        with pytest.raises(ValidationError):
            Snapshot.model_validate({**document, 'encounters': broken})
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'start_place': None, 'routes': []})


async def test_upgrades_a_format_21_document(client: AsyncClient, me: dict[str, str]):
    current = await published(client, me, await create_scenario(client, me))
    format_21 = {key: value for key, value in current.items() if key != 'encounters'}
    format_21['format'] = 21

    upgraded = upgrade_from_21(format_21)

    # 조우가 없던 때의 판이다
    assert (upgraded['format'], upgraded['encounters']) == (22, [])
    assert read_snapshot(format_21).encounters == []


# --- 테이블: 시작할 때 몬스터가 제자리에 놓인다 ---


async def test_starting_a_table_puts_every_monster_in_its_place(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    encounters = [
        encounter(world['gate'], world['rat'], 1),
        encounter(world['deep'], world['skeleton'], 1),
        encounter(world['deep'], world['rat'], 2),
    ]
    scenario = await create_scenario(client, me, **with_map(world, encounters=encounters))
    await published(client, me, scenario)

    table = await start_table(client, me, scenario)

    rows = await monsters_of(session, table)
    found = {(str(row.monster_id), row.number, str(row.place_id)) for row in rows}
    # 같은 몬스터는 테이블 전체에서 조우의 순서대로 번호를 받는다. 입구의 쥐가 1, 깊은 수로의 쥐가 2, 3 이다
    assert found == {
        (world['rat']['id'], 1, world['gate']['id']),
        (world['rat']['id'], 2, world['deep']['id']),
        (world['rat']['id'], 3, world['deep']['id']),
        (world['skeleton']['id'], 1, world['deep']['id']),
    }
    # 숫자는 그 몬스터의 시트다. HP 는 가득 차 있고 살아 있다
    rat = next(row for row in rows if str(row.monster_id) == world['rat']['id'])
    skeleton = next(row for row in rows if str(row.monster_id) == world['skeleton']['id'])
    assert (rat.abilities, rat.max_hp, rat.hp, rat.status) == (RAT_SHEET['abilities'], 4, 4, NpcStatus.ALIVE)
    assert (skeleton.abilities, skeleton.max_hp, skeleton.hp) == (SKELETON_SHEET['abilities'], 13, 13)
    # 마리마다 자기 ID 가 있다. 판정이 겨누는 값이다
    assert len({row.id for row in rows}) == 4


async def test_a_table_without_encounters_has_no_monsters(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    # 몬스터 시트가 있어도 조우가 없으면 테이블에 몬스터가 없다
    scenario = await create_scenario(client, me, **with_map(world))
    await published(client, me, scenario)

    table = await start_table(client, me, scenario)

    assert await monsters_of(session, table) == []


async def test_monsters_do_not_show_to_the_people_at_the_table(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['skeleton'], 2)])
    )
    await published(client, me, scenario)
    table = await start_table(client, me, scenario)
    rows = await monsters_of(session, table)

    detail = await client.get(f'{TABLES_URL}/{table["id"]}', headers=me)
    events = await client.get(f'{TABLES_URL}/{table["id"]}/events', headers=me)

    # 아직 가 보지 않은 깊은 수로에 무엇이 있는지 테이블의 응답에도 이벤트에도 드러나지 않는다
    assert detail.status_code == events.status_code == status.HTTP_200_OK
    for response in (detail, events):
        assert world['skeleton']['id'] not in response.text
        assert '해골 병사' not in response.text
        assert all(str(row.id) not in response.text for row in rows)


async def test_a_failed_start_makes_no_monsters(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['rat'], 2)])
    )
    await published(client, me, scenario)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)

    # 캐릭터를 정하지 않았다. 시작이 거절되면 몬스터의 상태도 남지 않는다
    response = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert await monsters_of(session, table) == []


async def test_monsters_go_with_the_table(client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession):
    scenario = await create_scenario(
        client, me, **with_map(world, encounters=[encounter(world['deep'], world['rat'], 2)])
    )
    await published(client, me, scenario)
    table = await start_table(client, me, scenario)

    await session.execute(text('DELETE FROM game_tables WHERE id = :id'), {'id': table['id']})
    await session.commit()

    assert await session.scalar(text('SELECT count(*) FROM table_monsters')) == 0


# --- DB 의 마지막 방어선 ---


async def a_started_table(client: AsyncClient, me: dict[str, str], world: dict) -> uuid.UUID:
    scenario = await create_scenario(client, me, **with_map(world))
    await published(client, me, scenario)
    return uuid.UUID((await start_table(client, me, scenario))['id'])


def a_monster(table_id: uuid.UUID, **fields) -> TableMonster:
    values = {
        'table_id': table_id,
        'monster_id': uuid.uuid4(),
        'number': 1,
        'place_id': uuid.uuid4(),
        'abilities': RAT_SHEET['abilities'],
        'max_hp': 4,
        'hp': 4,
        'status': NpcStatus.ALIVE,
    }
    values.update(fields)
    return TableMonster(**values)


@pytest.mark.parametrize(
    'fields',
    [
        {'hp': 5},
        {'hp': -1},
        {'hp': 0},
        {'hp': 2, 'status': NpcStatus.DEAD},
        {'status': 'fled'},
        {'number': 0},
        {'abilities': [10, 10]},
    ],
)
async def test_the_db_refuses_a_monster_that_does_not_add_up(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession, fields: dict
):
    table_id = await a_started_table(client, me, world)
    session.add(a_monster(table_id, **fields))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_db_refuses_the_same_number_twice(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    table_id = await a_started_table(client, me, world)
    monster_id = uuid.uuid4()
    session.add(a_monster(table_id, monster_id=monster_id, number=1))
    await session.commit()
    session.add(a_monster(table_id, monster_id=monster_id, number=1))

    with pytest.raises(IntegrityError):
        await session.commit()
