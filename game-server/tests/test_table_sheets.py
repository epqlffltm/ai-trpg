# game-server/tests/test_table_sheets.py

"""
테이블의 캐릭터 방식과 캐릭터 시트를 검증한다.

셋을 본다.
  - 방장이 테이블을 만들 때 캐릭터 방식을 판이 허용한 것 안에서 좁힌다.
  - 캐릭터는 이 테이블에서 허용한 방식으로만 정한다.
  - 게임을 시작하면 앉은 사람 모두가 시트를 받는다. 한 묶음으로, 전부 받거나 아무도 받지 않는다.

맨 아래에는 판단만 하는 작은 함수들(app/tables/sheets.py)의 테스트가 있다. DB 를 쓰지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CharacterMode, ScenarioVersion
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.tables import sheets
from app.tables.models import GameTable, TableMember, TableSheet
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
# 테스트에 쓰는 시트. 누구의 것인지 알아볼 수 있게 서로 다르게 둔다
ELF_SHEET = make_sheet(dex=16, max_hp=8)
LADY_SHEET = make_sheet(cha=18, max_hp=6)
DEFAULT_SHEET = make_sheet(con=14, max_hp=12)
PREGENS = [
    {'name': '폭주족 엘프', 'description': '귀가 길어서 헬멧을 못 쓴다.', 'sheet': ELF_SHEET},
    {'name': '악역영애', 'description': '바이크는 처음이지만 웃음소리는 크다.', 'sheet': LADY_SHEET},
]


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def publish_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """프리젠 둘과 기본 시트가 있는 시나리오를 만들고 판을 하나 낸다. 두 방식을 모두 허용한다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {
        'title': '17개 행성의 추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'pregens': PREGENS,
        'default_sheet': DEFAULT_SHEET,
    }
    body.update(fields)
    scenario = await client.post(SCENARIOS_URL, json=body, headers=headers)
    assert scenario.status_code == status.HTTP_201_CREATED, scenario.text
    published = await client.post(f'{SCENARIOS_URL}/{scenario.json()["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    return scenario.json()


async def create_table(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields):
    """판으로 테이블을 만드는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    body.update(fields)
    return await client.post(TABLES_URL, json=body, headers=headers)


async def open_table(client: AsyncClient, headers: dict[str, str], scenario: dict | None = None, **fields) -> dict:
    """테이블을 연다. 시나리오를 주지 않으면 두 방식을 모두 허용하는 시나리오를 새로 만든다."""
    scenario = scenario or await publish_scenario(client, headers)
    response = await create_table(client, headers, scenario, **fields)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def set_character(client: AsyncClient, headers: dict[str, str], table: dict, **fields):
    """캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/character'), json=fields, headers=headers)


async def start(client: AsyncClient, headers: dict[str, str], table: dict):
    return await client.post(table_url(table, '/start'), headers=headers)


async def read(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def sheets_of(table: dict) -> list[dict | None]:
    """앉은 사람들의 시트. 들어온 순서다."""
    return [member['sheet'] for member in table['members']]


def in_play(sheet: dict) -> dict:
    """판의 시트가 테이블에서 시작할 때의 모양. HP 가 가득 차 있다."""
    return {**sheet, 'hp': sheet['max_hp']}


async def count_sheets(session: AsyncSession) -> int:
    return await session.scalar(text('SELECT count(*) FROM table_sheets'))


# --- 테이블을 만들 때: 방식을 좁힌다 ---


async def test_a_table_allows_what_the_version_allows_unless_the_host_narrows_it(
    client: AsyncClient, me: dict[str, str]
):
    table = await open_table(client, me)

    assert table['character_modes'] == ['pregen', 'custom']
    assert table['default_sheet'] == DEFAULT_SHEET
    assert [pregen['sheet'] for pregen in table['pregens']] == [ELF_SHEET, LADY_SHEET]


async def test_the_table_shows_the_rules_but_not_the_gm_guide(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    # 능력치의 이름과 난이도의 단계는 앉은 사람에게 필요하다. 진행 지침은 AI 만 본다
    assert table['rules'] == SRD5.model_dump(mode='json')
    assert GM_GUIDE not in str(table)


@pytest.mark.parametrize(
    ('chosen', 'default_sheet'),
    [(['pregen'], None), (['custom'], DEFAULT_SHEET), (['custom', 'pregen'], DEFAULT_SHEET)],
)
async def test_the_host_narrows_the_modes(
    client: AsyncClient, me: dict[str, str], chosen: list[str], default_sheet: dict | None
):
    table = await open_table(client, me, character_modes=chosen)

    assert table['character_modes'] == [mode for mode in ('pregen', 'custom') if mode in chosen]
    # 직접 만들기를 막은 테이블은 기본 시트를 보여 주지 않는다. 받을 사람이 없다
    assert table['default_sheet'] == default_sheet


@pytest.mark.parametrize(('allowed', 'chosen'), [(['pregen'], ['custom']), (['pregen'], ['pregen', 'custom'])])
async def test_the_host_cannot_widen_the_modes(
    client: AsyncClient, me: dict[str, str], allowed: list[str], chosen: list[str]
):
    scenario = await publish_scenario(client, me, character_modes=allowed)

    response = await create_table(client, me, scenario, character_modes=chosen)

    # 제작자가 허용하지 않은 방식은 방장이 켤 수 없다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'character_modes' in response.json()['detail']


@pytest.mark.parametrize('chosen', [[], ['point_buy'], ['pregen', 'pregen'], 'pregen'])
async def test_rejects_modes_with_a_bad_shape(client: AsyncClient, me: dict[str, str], chosen):
    scenario = await publish_scenario(client, me)

    response = await create_table(client, me, scenario, character_modes=chosen)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(('capacity', 'expected'), [(2, status.HTTP_201_CREATED), (3, status.HTTP_409_CONFLICT)])
async def test_a_pregen_only_table_seats_no_more_than_its_pregens(
    client: AsyncClient, me: dict[str, str], capacity: int, expected: int
):
    by_the_host = await publish_scenario(client, me)
    by_the_creator = await publish_scenario(client, me, character_modes=['pregen'])

    # 프리젠이 둘이다. 프리젠 하나는 한 사람만 고르니, 프리젠만 허용하면 둘까지만 앉는다.
    # 방장이 좁혔든 제작자가 그렇게 정했든 같다
    narrowed = await create_table(client, me, by_the_host, capacity=capacity, character_modes=['pregen'])
    inherited = await create_table(client, me, by_the_creator, capacity=capacity)

    assert (narrowed.status_code, inherited.status_code) == (expected, expected)
    if expected == status.HTTP_409_CONFLICT:
        assert (narrowed.json()['reason'], inherited.json()['reason']) == ('pregens_too_few', 'pregens_too_few')


async def test_pregens_do_not_limit_a_table_where_characters_can_be_made(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=4)

    assert table['capacity'] == 4


# --- 캐릭터를 정할 때: 허용한 방식만 ---


@pytest.mark.parametrize(
    ('modes', 'character', 'expected'),
    [
        (['pregen'], {'pregen_index': 0}, status.HTTP_200_OK),
        (['pregen'], {'name': '떠돌이 요리사'}, status.HTTP_409_CONFLICT),
        (['custom'], {'name': '떠돌이 요리사'}, status.HTTP_200_OK),
        (['custom'], {'pregen_index': 0}, status.HTTP_409_CONFLICT),
        # 프리젠을 고르면서 이름을 고쳐 써도 프리젠을 고른 것이다
        (['custom'], {'pregen_index': 0, 'name': '은퇴한 폭주족'}, status.HTTP_409_CONFLICT),
        (['pregen'], {'pregen_index': 0, 'name': '은퇴한 폭주족'}, status.HTTP_200_OK),
    ],
)
async def test_a_character_is_made_only_in_a_mode_the_table_allows(
    client: AsyncClient, me: dict[str, str], modes: list[str], character: dict, expected: int
):
    table = await open_table(client, me, character_modes=modes)

    response = await set_character(client, me, table, **character)

    assert response.status_code == expected
    if expected == status.HTTP_409_CONFLICT:
        assert response.json()['reason'] == 'character_mode_not_allowed'
        # 거절된 요청은 캐릭터를 바꾸지 않는다
        assert (await read(client, me, table))['members'][0]['character'] is None


# --- 시작할 때: 시트를 받는다 ---


async def test_no_one_has_a_sheet_before_the_table_starts(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)

    changed = (await set_character(client, me, table, pregen_index=0)).json()

    # 캐릭터를 정해도 시트는 아직 없다. 모집 중에는 바뀔 숫자가 없다. 받을 숫자는 프리젠의 목록에서 본다
    assert sheets_of(changed) == [None]
    assert changed['pregens'][0]['sheet'] == ELF_SHEET
    assert await count_sheets(session) == 0


async def test_starting_gives_everyone_the_sheet_of_their_character(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, me, table, pregen_index=1)
    await set_character(client, friend, table, name='떠돌이 요리사')

    started = (await start(client, me, table)).json()

    # 프리젠을 고른 사람은 그 프리젠의 시트를, 직접 만든 사람은 기본 시트를 받는다. HP 는 가득 찬 채로 시작한다
    assert sheets_of(started) == [in_play(LADY_SHEET), in_play(DEFAULT_SHEET)]
    # 앉은 사람은 서로의 시트를 본다
    assert sheets_of(await read(client, friend, table)) == sheets_of(started)


async def test_a_renamed_pregen_keeps_the_sheet_of_the_pregen(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await set_character(client, me, table, pregen_index=0, name='은퇴한 폭주족')

    started = (await start(client, me, table)).json()

    assert started['members'][0]['character']['name'] == '은퇴한 폭주족'
    assert sheets_of(started) == [in_play(ELF_SHEET)]


async def test_the_sheet_follows_the_last_choice_of_character(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await set_character(client, me, table, pregen_index=0)
    await set_character(client, me, table, name='떠돌이 요리사')

    started = (await start(client, me, table)).json()

    # 프리젠을 골랐다가 직접 만든 것으로 바꿨다. 시작할 때의 캐릭터가 받을 시트를 정한다
    assert sheets_of(started) == [in_play(DEFAULT_SHEET)]


async def test_no_one_gets_a_sheet_when_the_start_is_refused(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, me, table, pregen_index=0)

    refused = await start(client, me, table)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'characters_missing'
    # 캐릭터를 정한 사람도 받지 않는다. 몇 사람만 시트를 가진 테이블은 없다
    assert sheets_of(await read(client, me, table)) == [None, None]
    assert await count_sheets(session) == 0


async def test_the_start_is_recorded_with_the_sheets(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await set_character(client, me, table, pregen_index=0)
    await start(client, me, table)

    events = (await client.get(table_url(table, '/events'), headers=me)).json()['items']

    started = next(event for event in events if event['type'] == 'table_started')
    # 뒤에 HP 가 바뀐 일들이 이벤트로 쌓인다. 처음의 값이 기록에 있어야 과정을 따라갈 수 있다
    assert started['payload']['members'] == [{'user_id': str(ME), 'character_name': '폭주족 엘프', 'sheet': ELF_SHEET}]


async def test_the_sheet_goes_when_its_owner_leaves(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, me, table, pregen_index=0)
    await set_character(client, friend, table, pregen_index=1)
    await start(client, me, table)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)

    assert left.status_code == status.HTTP_204_NO_CONTENT
    assert sheets_of(await read(client, me, table)) == [in_play(ELF_SHEET)]
    assert await count_sheets(session) == 1


async def test_a_table_from_a_version_without_sheets_starts_with_baseline_sheets(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    scenario = await publish_scenario(client, me)
    # 캐릭터에 숫자가 없던 때(형식 4)에 굳힌 판. 프리젠에 시트가 없고, 방식도 기본 시트도 없다
    current = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/versions/1', headers=me)).json()['snapshot']
    old = {key: value for key, value in current.items() if key not in ('character_modes', 'default_sheet')}
    old['pregens'] = [{'name': '옛 엘프', 'description': ''}]
    old['format'] = 4
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=2, snapshot=old))
    await session.commit()

    table = await open_table(client, me, scenario, version=2, capacity=1)
    await set_character(client, me, table, pregen_index=0)
    started = (await start(client, me, table)).json()

    # 옛 판은 두 방식을 모두 허용한 것으로, 시트는 기준 시트(모든 능력치 10, 최대 HP 10)로 읽는다
    assert table['character_modes'] == ['pregen', 'custom']
    assert sheets_of(started) == [in_play(SHEET)]


# --- DB 의 마지막 방어선 ---


async def seat_someone(session: AsyncSession) -> TableMember:
    """시작한 테이블에 앉아 시트를 가진 사람 하나를 DB 에서 꺼낸다."""
    member = (await session.execute(text('SELECT table_id, user_id FROM table_members LIMIT 1'))).one()
    return await session.get(TableMember, (member.table_id, member.user_id))


@pytest.fixture
async def started_table(client: AsyncClient, me: dict[str, str]) -> dict:
    """혼자 앉아 시작한 테이블."""
    table = await open_table(client, me, capacity=1)
    await set_character(client, me, table, pregen_index=0)
    return (await start(client, me, table)).json()


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        ('hp = max_hp + 1', 'hp_range'),
        ('hp = -1', 'hp_range'),
        ('max_hp = 0, hp = 0', 'max_hp_positive'),
    ],
)
async def test_the_database_rejects_impossible_hit_points(
    started_table: dict, session: AsyncSession, change: str, constraint: str
):
    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE table_sheets SET {change}'))


async def test_the_database_allows_hit_points_at_both_ends(started_table: dict, session: AsyncSession):
    await session.execute(text('UPDATE table_sheets SET hp = 0'))
    await session.execute(text('UPDATE table_sheets SET hp = max_hp'))
    await session.commit()


async def test_the_database_gives_one_sheet_to_one_member(started_table: dict, session: AsyncSession):
    member = await seat_someone(session)
    session.add(TableSheet(table_id=member.table_id, user_id=member.user_id, abilities={}, max_hp=1, hp=1))

    with pytest.raises(IntegrityError, match='uq_table_sheets'):
        await session.commit()


async def test_the_database_gives_no_sheet_to_someone_who_is_not_seated(started_table: dict, session: AsyncSession):
    session.add(TableSheet(table_id=uuid.UUID(started_table['id']), user_id=FRIEND, abilities={}, max_hp=1, hp=1))

    with pytest.raises(IntegrityError, match='fk_table_sheets'):
        await session.commit()


@pytest.mark.parametrize('modes', [[], ['point_buy'], ['pregen', 'point_buy']])
async def test_the_database_rejects_modes_it_does_not_know(
    started_table: dict, session: AsyncSession, modes: list[str]
):
    change = text('UPDATE game_tables SET character_modes = CAST(:modes AS varchar[])')

    with pytest.raises(IntegrityError, match='character_modes_allowed'):
        await session.execute(change, {'modes': modes})


# --- 판단만 하는 작은 함수들. DB 를 쓰지 않는다 ---

BOTH = [CharacterMode.PREGEN, CharacterMode.CUSTOM]


def make_snapshot(default_sheet: dict | None = DEFAULT_SHEET) -> Snapshot:
    """프리젠 둘이 있는 판. 기본 시트는 바꿔 볼 수 있다."""
    return read_snapshot(
        {
            'format': 5,
            'title': '판',
            'description': '',
            'rating': 'all',
            'openings': ['도입부'],
            'recommended_players': {'min': 1, 'max': 4},
            'pregens': PREGENS,
            'character_modes': ['pregen', 'custom'],
            'default_sheet': default_sheet,
            'rulebook': {'id': str(ME), 'title': '룰북', 'gm_guide': '', 'rules': SRD5.model_dump(mode='json')},
            'world': None,
            'lorebooks': [],
        }
    )


def make_member(name: str | None = '아무개', pregen_index: int | None = None) -> TableMember:
    return TableMember(user_id=uuid.uuid4(), character_name=name, pregen_index=pregen_index)


@pytest.mark.parametrize(
    ('allowed', 'chosen', 'expected'),
    [
        (BOTH, None, BOTH),
        (BOTH, [CharacterMode.PREGEN], [CharacterMode.PREGEN]),
        (BOTH, [CharacterMode.CUSTOM], [CharacterMode.CUSTOM]),
        (BOTH, BOTH, BOTH),
        ([CharacterMode.PREGEN], None, [CharacterMode.PREGEN]),
        # 넓힐 수 없다
        ([CharacterMode.PREGEN], [CharacterMode.CUSTOM], None),
        ([CharacterMode.PREGEN], BOTH, None),
    ],
)
def test_narrows_the_modes(allowed: list, chosen: list | None, expected: list | None):
    assert sheets.narrow_modes(allowed, chosen) == expected


@pytest.mark.parametrize(
    ('modes', 'expected'),
    [([CharacterMode.PREGEN], 2), ([CharacterMode.CUSTOM], None), (BOTH, None)],
)
def test_only_a_pregen_only_table_is_limited_by_its_pregens(modes: list, expected: int | None):
    assert sheets.seats_by_pregens(make_snapshot(), modes) == expected


def test_tells_the_mode_of_a_request():
    assert sheets.mode_of(0) == CharacterMode.PREGEN
    assert sheets.mode_of(None) == CharacterMode.CUSTOM


def test_finds_the_sheet_a_member_will_get():
    snapshot = make_snapshot()

    assert sheets.find_source(snapshot, make_member(pregen_index=1)).max_hp == LADY_SHEET['max_hp']
    assert sheets.find_source(snapshot, make_member()).max_hp == DEFAULT_SHEET['max_hp']
    # 캐릭터를 정하지 않은 사람은 받을 시트가 없다
    assert sheets.find_source(snapshot, make_member(name=None)) is None
    # 직접 만들었는데 판에 기본 시트가 없으면 받을 시트가 없다
    assert sheets.find_source(make_snapshot(default_sheet=None), make_member()) is None


def test_a_new_sheet_starts_at_full_hit_points_and_is_its_own_copy():
    source = make_snapshot().pregens[0].sheet

    sheet = sheets.new_sheet(source)
    sheet.abilities['dex'] = 1

    assert (sheet.max_hp, sheet.hp) == (ELF_SHEET['max_hp'], ELF_SHEET['max_hp'])
    # 테이블의 시트를 고쳐도 판의 시트는 그대로다
    assert source.abilities['dex'] == ELF_SHEET['abilities']['dex']


def test_hands_out_sheets_to_everyone_or_to_no_one():
    ready = GameTable(members=[make_member(pregen_index=0), make_member()])
    not_ready = GameTable(members=[make_member(pregen_index=0), make_member(name=None)])

    assert sheets.hand_out(ready, make_snapshot()) is True
    assert [member.sheet.max_hp for member in ready.members] == [ELF_SHEET['max_hp'], DEFAULT_SHEET['max_hp']]
    assert sheets.hand_out(not_ready, make_snapshot()) is False
    assert [member.sheet for member in not_ready.members] == [None, None]
