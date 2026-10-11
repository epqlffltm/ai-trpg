# game-server/tests/test_npc_sheets.py

"""
NPC 시트와 NPC 의 상태(#111 ①)를 검증한다.

넷을 본다.
  - 시나리오: NPC 시트와 기본 NPC 시트를 적고 읽고 고친다. 모양만 본다.
  - 게시: 시트가 붙인 로어북의 인물 항목을 가리키는지, 규칙에 맞는지, 시트가 없는 인물이 받을 숫자가 있는지.
  - 판: 형식 13 에 실린다. 옛 판은 NPC 시트 없이, 기본 NPC 시트는 기준 시트로 읽는다.
  - 테이블: 시작할 때 인물마다 상태가 생긴다. DB 가 HP 와 생사가 어긋나는 것을 막는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ScenarioVersion
from app.assets.scenarios.snapshot import (
    SNAPSHOT_FORMAT,
    Snapshot,
    npc_sheet_of,
    person_entries,
    read_snapshot,
    upgrade_from_12,
)
from app.engine.sheet import Sheet
from app.main import API_PREFIX
from app.tables.models import NpcStatus, TableNpc
from app.tables.npcs import make_npcs
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 누구의 숫자인지 알아볼 수 있게 서로 다르게 둔다
LADY_SHEET = make_sheet(cha=18, max_hp=14)
DWARF_SHEET = make_sheet(str=17, max_hp=30)
NPC_DEFAULT = make_sheet(con=12, max_hp=7)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def add_entry(client: AsyncClient, headers: dict[str, str], lorebook: dict, name: str, kind: str) -> dict:
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    return await post(client, url, headers, name=name, keywords=[], content=f'{name}의 설명', kind=kind)


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """인물 둘(악역영애, 드워프)과 장소 하나가 든 로어북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    return {
        'lorebook': lorebook,
        'lady': await add_entry(client, me, lorebook, '악역영애', 'person'),
        'dwarf': await add_entry(client, me, lorebook, '드워프', 'person'),
        'highway': await add_entry(client, me, lorebook, '우주 고속도로', 'place'),
    }


async def create_scenario(client: AsyncClient, headers: dict[str, str], lore: dict | None, **fields) -> dict:
    """룰북, 스타팅, 기본 시트가 있는 시나리오. lore 를 주면 그 로어북을 붙인다."""
    rulebook = await post(client, RULEBOOKS_URL, headers, title='룰북')
    body = {
        'title': '열일곱 행성 추격전',
        'rulebook_id': rulebook['id'],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']] if lore else [],
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


def npc(entry: dict, sheet: dict) -> dict:
    return {'entry_id': entry['id'], 'sheet': sheet}


# --- 시나리오: 적고 읽고 고친다 ---


async def test_npc_sheets_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['npc_sheets'] == [npc(lore['lady'], LADY_SHEET)]
    assert read['default_npc_sheet'] == NPC_DEFAULT


async def test_a_scenario_starts_without_npc_sheets(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    assert (scenario['npc_sheets'], scenario['default_npc_sheet']) == ([], None)


async def test_the_same_person_cannot_have_two_sheets(client: AsyncClient, me: dict[str, str], lore: dict):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    twice = [npc(lore['lady'], LADY_SHEET), npc(lore['lady'], DWARF_SHEET)]

    response = await client.post(
        SCENARIOS_URL, json={'title': '추격전', 'rulebook_id': rulebook['id'], 'npc_sheets': twice}, headers=me
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'npc_sheet',
    [
        # 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 칸을 만들지 않는다
        {'entry_id': NO_SUCH_ID},
        {'entry_id': NO_SUCH_ID, 'sheet': None},
        # 모양이 틀린 시트
        {'entry_id': NO_SUCH_ID, 'sheet': {'abilities': {}, 'max_hp': 0}},
        # 모르는 칸
        {'entry_id': NO_SUCH_ID, 'sheet': SHEET, 'hp': 3},
    ],
)
async def test_an_npc_sheet_must_have_the_shape_of_a_sheet(client: AsyncClient, me: dict[str, str], npc_sheet: dict):
    response = await client.post(SCENARIOS_URL, json={'title': '추격전', 'npc_sheets': [npc_sheet]}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_updating_replaces_npc_sheets_and_clears_the_default(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )

    response = await client.patch(
        f'{SCENARIOS_URL}/{scenario["id"]}',
        json={'npc_sheets': [npc(lore['dwarf'], DWARF_SHEET)], 'default_npc_sheet': None},
        headers=me,
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['npc_sheets'] == [npc(lore['dwarf'], DWARF_SHEET)]
    assert response.json()['default_npc_sheet'] is None


async def test_updating_without_the_fields_keeps_them(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )

    response = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'title': '새 제목'}, headers=me)

    assert response.json()['npc_sheets'] == [npc(lore['lady'], LADY_SHEET)]
    assert response.json()['default_npc_sheet'] == NPC_DEFAULT


# --- 게시 ---


async def test_the_snapshot_carries_npc_sheets(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )

    snapshot = await published(client, me, scenario)

    assert snapshot['format'] == SNAPSHOT_FORMAT
    assert snapshot['npc_sheets'] == [npc(lore['lady'], LADY_SHEET)]
    assert snapshot['default_npc_sheet'] == NPC_DEFAULT


async def test_a_person_without_a_sheet_needs_the_default(client: AsyncClient, me: dict[str, str], lore: dict):
    scenario = await create_scenario(client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)])

    # 드워프가 받을 숫자가 없다
    assert await refused(client, me, scenario) == ['default_npc_sheet_missing']


async def test_when_every_person_has_a_sheet_no_default_is_needed(client: AsyncClient, me: dict[str, str], lore: dict):
    sheets = [npc(lore['lady'], LADY_SHEET), npc(lore['dwarf'], DWARF_SHEET)]
    scenario = await create_scenario(client, me, lore, npc_sheets=sheets)

    snapshot = await published(client, me, scenario)

    # 장소에는 숫자가 없다. 인물만 센다
    assert snapshot['default_npc_sheet'] is None


async def test_without_people_no_default_is_needed(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None)

    snapshot = await published(client, me, scenario)

    assert (snapshot['npc_sheets'], snapshot['default_npc_sheet']) == ([], None)


async def test_a_sheet_for_an_entry_that_is_not_attached_is_refused(
    client: AsyncClient, me: dict[str, str], lore: dict
):
    other = await post(client, LOREBOOKS_URL, me, title='다른 로어북')
    stranger = await add_entry(client, me, other, '낯선 기사', 'person')
    sheets = [npc(stranger, LADY_SHEET), {'entry_id': NO_SUCH_ID, 'sheet': LADY_SHEET}]
    scenario = await create_scenario(client, me, lore, npc_sheets=sheets, default_npc_sheet=NPC_DEFAULT)

    # 붙이지 않은 로어북의 인물도, 없는 항목도 같은 이유다. 둘이어도 한 번만 적는다
    assert await refused(client, me, scenario) == ['npc_sheet_entry_missing']


async def test_detaching_the_lorebook_leaves_the_sheet_pointing_at_nothing(
    client: AsyncClient, me: dict[str, str], lore: dict
):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'lorebook_ids': []}, headers=me)

    assert await refused(client, me, scenario) == ['npc_sheet_entry_missing']


async def test_a_sheet_for_something_that_is_not_a_person_is_refused(
    client: AsyncClient, me: dict[str, str], lore: dict
):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['highway'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )

    assert await refused(client, me, scenario) == ['npc_sheet_not_person']


@pytest.mark.parametrize('sheet', [make_sheet(str=21), {'abilities': {'str': 10}, 'max_hp': 5}])
async def test_npc_sheets_must_fit_the_rules(client: AsyncClient, me: dict[str, str], lore: dict, sheet: dict):
    as_npc = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], sheet)], default_npc_sheet=NPC_DEFAULT
    )
    as_default = await create_scenario(client, me, lore, default_npc_sheet=sheet)

    assert await refused(client, me, as_npc) == ['npc_sheet_invalid']
    assert await refused(client, me, as_default) == ['default_npc_sheet_invalid']


async def test_a_default_npc_sheet_is_checked_even_when_it_is_not_needed(client: AsyncClient, me: dict[str, str]):
    scenario = await create_scenario(client, me, None, default_npc_sheet=make_sheet(str=21))

    assert await refused(client, me, scenario) == ['default_npc_sheet_invalid']


async def test_without_a_rulebook_npc_sheets_are_not_checked_against_rules(
    client: AsyncClient, me: dict[str, str], lore: dict
):
    scenario = await create_scenario(
        client,
        me,
        lore,
        rulebook_id=None,
        npc_sheets=[npc(lore['lady'], make_sheet(str=21))],
        default_npc_sheet=make_sheet(str=21),
    )

    assert await refused(client, me, scenario) == ['rulebook_missing']


# --- 판: 계약과 옛 판 ---


def entry(name: str, kind: str) -> dict:
    return {'id': str(uuid.uuid4()), 'name': name, 'keywords': [], 'content': '', 'kind': kind}


async def current_snapshot(client: AsyncClient, headers: dict[str, str]) -> dict:
    """인물도 NPC 시트도 없는 지금 형식의 판 하나."""
    return await published(client, headers, await create_scenario(client, headers, None))


def with_people(document: dict, *entries: dict) -> dict:
    return {**document, 'lorebooks': [{'id': str(uuid.uuid4()), 'title': '인물', 'entries': list(entries)}]}


async def test_a_snapshot_with_an_uncovered_person_and_no_default_is_invalid(client: AsyncClient, me: dict[str, str]):
    lady = entry('악역영애', 'person')
    document = with_people(await current_snapshot(client, me), lady, entry('고속도로', 'place'))

    # 게시가 막는 것을 판의 계약도 막는다. 시작하는 쪽은 인물마다 숫자가 있다고 믿는다
    with pytest.raises(ValidationError):
        Snapshot.model_validate(document)
    covered = Snapshot.model_validate({**document, 'npc_sheets': [{'entry_id': lady['id'], 'sheet': LADY_SHEET}]})
    assert covered.default_npc_sheet is None


async def test_a_person_gets_its_own_sheet_or_the_default(client: AsyncClient, me: dict[str, str]):
    lady, dwarf, highway = entry('악역영애', 'person'), entry('드워프', 'person'), entry('고속도로', 'place')
    document = with_people(await current_snapshot(client, me), lady, highway, dwarf)
    document['npc_sheets'] = [{'entry_id': lady['id'], 'sheet': LADY_SHEET}]
    document['default_npc_sheet'] = NPC_DEFAULT

    snapshot = Snapshot.model_validate(document)

    assert [person.name for person in person_entries(snapshot)] == ['악역영애', '드워프']
    assert npc_sheet_of(snapshot, uuid.UUID(lady['id'])) == Sheet(**LADY_SHEET)
    assert npc_sheet_of(snapshot, uuid.UUID(dwarf['id'])) == Sheet(**NPC_DEFAULT)


async def test_upgrades_a_format_12_document(client: AsyncClient, me: dict[str, str]):
    current = with_people(await current_snapshot(client, me), entry('악역영애', 'person'))
    format_12 = {key: value for key, value in current.items() if key not in ('npc_sheets', 'default_npc_sheet')}
    format_12['format'] = 12

    upgraded = upgrade_from_12(format_12)

    # NPC 에 숫자가 없던 때의 판이다. 인물은 모두 기준 시트(모든 능력치 10, 최대 HP 10)를 쓴다
    assert upgraded['format'] == 13
    assert (upgraded['npc_sheets'], upgraded['default_npc_sheet']) == ([], SHEET)
    assert read_snapshot(format_12).default_npc_sheet == Sheet(**SHEET)
    # 받은 문서는 고치지 않는다
    assert format_12['format'] == 12
    assert 'npc_sheets' not in format_12


# --- 테이블: 시작할 때 인물마다 상태가 생긴다 ---


async def start_table(client: AsyncClient, headers: dict[str, str], scenario: dict, version: int = 1) -> dict:
    """혼자 앉아 기본 시트로 캐릭터를 정하고 시작한 테이블."""
    body = {'scenario_id': scenario['id'], 'version': version, 'capacity': 1}
    table = await post(client, TABLES_URL, headers, **body)
    character = await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '카이'}, headers=headers)
    assert character.status_code == status.HTTP_200_OK, character.text
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=headers)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def npcs_of(session: AsyncSession, table: dict) -> dict[str, TableNpc]:
    """테이블의 NPC 상태들. 항목의 ID(글자)로 찾는다."""
    rows = await session.scalars(select(TableNpc).where(TableNpc.table_id == uuid.UUID(table['id'])))
    return {str(row.entry_id): row for row in rows}


async def test_starting_a_table_makes_a_state_for_every_person(
    client: AsyncClient, me: dict[str, str], lore: dict, session: AsyncSession
):
    scenario = await create_scenario(
        client, me, lore, npc_sheets=[npc(lore['lady'], LADY_SHEET)], default_npc_sheet=NPC_DEFAULT
    )
    await published(client, me, scenario)

    table = await start_table(client, me, scenario)

    states = await npcs_of(session, table)
    # 장소에는 상태가 없다
    assert set(states) == {lore['lady']['id'], lore['dwarf']['id']}
    lady, dwarf = states[lore['lady']['id']], states[lore['dwarf']['id']]
    # 자기 시트가 있으면 그것, 없으면 기본 NPC 시트다. HP 는 가득 차 있고 살아 있다
    assert (lady.abilities, lady.max_hp, lady.hp, lady.status) == (LADY_SHEET['abilities'], 14, 14, NpcStatus.ALIVE)
    assert (dwarf.abilities, dwarf.max_hp, dwarf.hp) == (NPC_DEFAULT['abilities'], 7, 7)


async def test_a_table_without_people_has_no_npc_states(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    scenario = await create_scenario(client, me, None)
    await published(client, me, scenario)

    table = await start_table(client, me, scenario)

    assert await npcs_of(session, table) == {}


async def test_a_table_from_a_version_without_npc_sheets_uses_baseline_sheets(
    client: AsyncClient, me: dict[str, str], lore: dict, session: AsyncSession
):
    scenario = await create_scenario(client, me, lore, default_npc_sheet=NPC_DEFAULT)
    current = await published(client, me, scenario)
    # NPC 에 숫자가 없던 때(형식 12)에 굳힌 판
    old = {key: value for key, value in current.items() if key not in ('npc_sheets', 'default_npc_sheet')}
    old['format'] = 12
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=2, snapshot=old))
    await session.commit()

    table = await start_table(client, me, scenario, version=2)

    states = await npcs_of(session, table)
    assert {(row.max_hp, row.hp) for row in states.values()} == {(10, 10)}
    assert len(states) == 2


async def test_a_failed_start_makes_no_npc_states(
    client: AsyncClient, me: dict[str, str], lore: dict, session: AsyncSession
):
    scenario = await create_scenario(client, me, lore, default_npc_sheet=NPC_DEFAULT)
    await published(client, me, scenario)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)

    # 캐릭터를 정하지 않았다. 시작이 거절되면 NPC 의 상태도 남지 않는다
    response = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert await npcs_of(session, table) == {}


async def test_npc_states_go_with_the_table(client: AsyncClient, me: dict[str, str], lore: dict, session: AsyncSession):
    scenario = await create_scenario(client, me, lore, default_npc_sheet=NPC_DEFAULT)
    await published(client, me, scenario)
    table = await start_table(client, me, scenario)

    await session.execute(text('DELETE FROM game_tables WHERE id = :id'), {'id': table['id']})
    await session.commit()

    assert await session.scalar(text('SELECT count(*) FROM table_npcs')) == 0


# --- DB 의 마지막 방어선 ---


@pytest.fixture
async def an_npc(client: AsyncClient, me: dict[str, str], lore: dict, session: AsyncSession) -> TableNpc:
    """시작한 테이블의 NPC 하나(드워프, 기본 NPC 시트)."""
    scenario = await create_scenario(client, me, lore, default_npc_sheet=NPC_DEFAULT)
    await published(client, me, scenario)
    table = await start_table(client, me, scenario)
    return (await npcs_of(session, table))[lore['dwarf']['id']]


@pytest.mark.parametrize(
    ('hp', 'npc_status'),
    [
        # 살아 있는데 HP 가 없다
        (0, NpcStatus.ALIVE),
        # 쓰러지거나 죽었는데 HP 가 남아 있다
        (3, NpcStatus.DOWNED),
        (3, NpcStatus.DEAD),
        # HP 가 범위 밖이다
        (-1, NpcStatus.DOWNED),
        (8, NpcStatus.ALIVE),
        # 모르는 생사
        (3, 'sleeping'),
    ],
)
async def test_the_db_refuses_hp_and_status_that_disagree(
    an_npc: TableNpc, session: AsyncSession, hp: int, npc_status: str
):
    an_npc.hp = hp
    an_npc.status = npc_status

    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.parametrize('npc_status', [NpcStatus.DOWNED, NpcStatus.DEAD])
async def test_the_db_accepts_a_person_at_zero_hp_downed_or_dead(
    an_npc: TableNpc, session: AsyncSession, npc_status: NpcStatus
):
    an_npc.hp = 0
    an_npc.status = npc_status

    await session.commit()


# --- 상태를 만드는 작은 함수(app/tables/npcs.py). DB 를 쓰지 않는다 ---


async def test_states_are_made_in_the_order_of_the_people(client: AsyncClient, me: dict[str, str]):
    lady, dwarf = entry('악역영애', 'person'), entry('드워프', 'person')
    document = with_people(await current_snapshot(client, me), dwarf, entry('고속도로', 'place'), lady)
    document['default_npc_sheet'] = NPC_DEFAULT
    snapshot = Snapshot.model_validate(document)
    table_id = uuid.uuid4()

    states = make_npcs(table_id, snapshot)

    assert [str(state.entry_id) for state in states] == [dwarf['id'], lady['id']]
    assert all(state.table_id == table_id for state in states)
    # 숫자는 복사한다. 상태의 능력치를 바꿔도 판은 그대로다
    states[0].abilities['str'] = 1
    assert snapshot.default_npc_sheet.abilities['str'] == NPC_DEFAULT['abilities']['str']
