# game-server/tests/test_character_mode.py

"""
자리에 적어 두는 캐릭터의 방식(table_members.character_mode)을 검증한다.

캐릭터를 어느 방식으로 얻었는지를 자리에 적는다. 숫자가 어디서 왔는지는 테이블의 모두가 본다.
능력치만 봐서는 직접 적은 것인지 다른 방식으로 정한 것인지 알 수 없어서 따로 적는다.

보는 것은 셋이다.
  - 캐릭터를 정하면 방식이 적히고, 방식을 바꾸면 따라 바뀐다. 앉은 사람 모두에게 보인다.
  - 이 칸이 생기기 전에 만든 캐릭터에는 마이그레이션이 방식을 채운다.
  - 방식과 자리의 다른 칸(이름, 프리젠, 능력치)이 어긋난 행은 DB 가 받지 않는다.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

MIGRATIONS = Path(__file__).parent.parent / 'migrations' / 'versions'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

ABILITIES = SHEET['abilities']


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


async def open_table(client: AsyncClient, headers: dict[str, str]) -> dict:
    """프리젠, 기본 시트, 직접 적기를 모두 허용하는 시나리오로 두 사람이 앉는 테이블을 연다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=headers)
    body = {
        'title': '17개 행성의 추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'pregens': [{'name': '폭주족 엘프', 'sheet': SHEET}],
        'default_sheet': SHEET,
        'character_modes': ['pregen', 'custom', 'manual'],
        'player_made_hp': {'base': 10, 'cap': 12},
    }
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=headers)).json()
    version = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)
    assert version.status_code == status.HTTP_201_CREATED, version.text
    table = await client.post(
        TABLES_URL, json={'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}, headers=headers
    )
    assert table.status_code == status.HTTP_201_CREATED, table.text
    return table.json()


async def set_character(client: AsyncClient, headers: dict[str, str], table: dict, **fields) -> dict:
    """캐릭터를 정하고, 그 뒤의 테이블을 돌려준다."""
    response = await client.put(table_url(table, '/character'), json=fields, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def mode_of(table: dict, user_id: uuid.UUID) -> str | None:
    """테이블의 응답에서 그 사람의 방식을 꺼낸다."""
    return next(member['character_mode'] for member in table['members'] if member['user_id'] == str(user_id))


def load_migration(name: str):
    """마이그레이션 파일 하나를 모듈로 읽는다. 파일 이름 앞의 번호는 만들 때마다 달라서 뒤의 이름으로 찾는다."""
    (path,) = MIGRATIONS.glob(f'*_{name}.py')
    spec = importlib.util.spec_from_file_location(f'{name}_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- 캐릭터를 정하면 방식이 적힌다 ---


async def test_a_seat_without_a_character_has_no_mode(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    assert mode_of(table, ME) is None


@pytest.mark.parametrize(
    ('body', 'mode'),
    [
        ({'pregen_index': 0}, 'pregen'),
        ({'name': '드워프'}, 'custom'),
        ({'mode': 'custom', 'name': '드워프'}, 'custom'),
        ({'mode': 'manual', 'name': '드워프', 'abilities': ABILITIES}, 'manual'),
    ],
    ids=['pregen', 'custom', 'custom written out', 'manual'],
)
async def test_the_seat_remembers_how_the_character_was_made(
    client: AsyncClient, me: dict[str, str], body: dict, mode: str
):
    table = await open_table(client, me)

    table = await set_character(client, me, table, **body)

    assert mode_of(table, ME) == mode


async def test_changing_the_way_changes_the_mode(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    first = await set_character(client, me, table, mode='manual', name='드워프', abilities=ABILITIES)
    second = await set_character(client, me, table, pregen_index=0)
    third = await set_character(client, me, table, name='드워프')

    assert [mode_of(seen, ME) for seen in (first, second, third)] == ['manual', 'pregen', 'custom']


async def test_abilities_that_were_dropped_are_really_gone(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)
    await set_character(client, me, table, mode='manual', name='드워프', abilities=ABILITIES)

    await set_character(client, me, table, pregen_index=0)

    # 지운 능력치는 DB 에서도 없는 것(NULL)이어야 한다. JSON 의 null 이라는 값으로 남으면 DB 의 조건이 있다고 본다
    assert await session.scalar(text('SELECT abilities IS NULL FROM table_members')) is True


async def test_everyone_at_the_table_sees_the_mode(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await set_character(client, me, table, mode='manual', name='드워프', abilities=ABILITIES)

    seen = (await client.get(table_url(table), headers=friend)).json()

    # 숫자가 어디서 왔는지는 숨기지 않는다. 직접 적은 숫자인지를 같은 테이블의 사람이 안다
    assert mode_of(seen, ME) == 'manual'
    assert mode_of(seen, FRIEND) is None


# --- 이 칸이 생기기 전에 만든 캐릭터 ---


async def test_the_migration_fills_the_mode_of_characters_made_before(session: AsyncSession):
    # 조건이 걸린 진짜 표에는 옛 모양의 행을 넣을 수 없다. 같은 이름의 임시 표를 만들어 채우는 문장만 돌려 본다.
    # 임시 표는 진짜 표보다 먼저 찾아지고, 트랜잭션이 끝나면 사라진다
    await session.execute(
        text(
            'CREATE TEMP TABLE table_members '
            '(seat text, character_name text, pregen_index int, abilities jsonb, character_mode text) ON COMMIT DROP'
        )
    )
    await session.execute(
        text("""
            INSERT INTO table_members (seat, character_name, pregen_index, abilities) VALUES
                ('empty', NULL, NULL, NULL),
                ('pregen', '폭주족 엘프', 0, NULL),
                ('custom', '드워프', NULL, NULL),
                ('manual', '악역영애', NULL, '{"str": 20}'),
                ('custom after manual', '드워프', NULL, 'null')
        """)
    )
    migration = load_migration('member_character_mode')

    await session.execute(text(migration.CLEAR_JSON_NULLS))
    await session.execute(text(migration.BACKFILL))

    rows = await session.execute(text('SELECT seat, character_mode, abilities IS NULL FROM table_members'))
    assert {seat: (mode, is_null) for seat, mode, is_null in rows.all()} == {
        'empty': (None, True),
        'pregen': ('pregen', True),
        'custom': ('custom', True),
        'manual': ('manual', False),
        # 능력치를 적었다가 지운 자리다. JSON 의 null 이 남아 있었다. 능력치가 없는 것으로 읽혀야 한다
        'custom after manual': ('custom', True),
    }


# --- DB 가 마지막으로 막는다 ---


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        # 캐릭터가 없는데 방식만 있다
        ("character_mode = 'custom'", 'character_mode_needs_character'),
        # 모르는 방식
        ("""character_name = '엘프', character_mode = 'cheat', abilities = '{"str": 20}'""", 'character_mode_allowed'),
    ],
    ids=['mode without a character', 'unknown mode'],
)
async def test_the_database_rejects_a_bad_mode_on_an_empty_seat(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, change: str, constraint: str
):
    await open_table(client, me)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE table_members SET {change}'))


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        # 캐릭터가 있는데 방식이 없다
        ('character_mode = NULL', 'character_mode_needs_character'),
        # 프리젠 방식인데 프리젠을 차지하지 않았다
        ("character_mode = 'pregen'", 'pregen_needs_pregen_mode'),
        # 프리젠을 차지했는데 프리젠 방식이 아니다
        ('pregen_index = 0', 'pregen_needs_pregen_mode'),
        # 기본 시트를 받는 방식인데 직접 정한 능력치가 있다
        ("""abilities = '{"str": 20}'""", 'abilities_need_player_made_mode'),
        # 능력치를 정하는 방식인데 능력치가 없다
        ("character_mode = 'manual'", 'abilities_need_player_made_mode'),
        # 능력치가 묶음이 아니다. JSON 의 null 은 "없음"이 아니라 값이다
        ("character_mode = 'manual', abilities = 'null'", 'abilities_is_object'),
        ("character_mode = 'manual', abilities = '20'", 'abilities_is_object'),
    ],
    ids=[
        'no mode',
        'pregen mode without a pregen',
        'pregen without its mode',
        'abilities on custom',
        'no abilities',
        'json null as abilities',
        'a number as abilities',
    ],
)
async def test_the_database_rejects_a_mode_that_does_not_match_the_seat(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, change: str, constraint: str
):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE table_members SET {change}'))


async def test_the_database_rejects_abilities_on_a_pregen(client: AsyncClient, me: dict[str, str], session):
    table = await open_table(client, me)
    await set_character(client, me, table, pregen_index=0)

    # 프리젠의 숫자는 제작자가 적은 것이다. 그 위에 직접 정한 능력치가 얹힐 수 없다
    with pytest.raises(IntegrityError, match='abilities_need_player_made_mode'):
        await session.execute(text("""UPDATE table_members SET abilities = '{"str": 20}'"""))
