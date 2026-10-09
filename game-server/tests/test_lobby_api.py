# game-server/tests/test_lobby_api.py

"""
로비를 검증한다. 로비에 보이는 테이블의 목록과, 초대 코드 없이 들어가는 길.

보는 것은 넷이다.
  - 로비에 보일지는 방장이 테이블을 만들 때 정한다. 기본은 보이지 않는다.
  - 로비에는 들어갈 수 있는 테이블만 나온다. 모집 중이고, 자리가 남았고, 볼 수 있는 등급인 것.
  - 로비에 보이는 테이블에는 초대 코드 없이 들어간다. 보이지 않는 테이블에는 이 길로 들어갈 수 없다.
  - 비밀번호를 건 테이블은 비밀번호가 맞아야 들어간다. 비밀번호는 그대로 저장하지 않고, 응답에도 싣지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import TABLE_MAX_PLAYERS, Asset, AssetType, Scenario, ScenarioVersion
from app.main import API_PREFIX
from app.tables.models import TABLE_PASSWORD_MAX_LENGTH, TABLE_PASSWORD_MIN_LENGTH, GameTable, TableMember
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'
LOBBY_URL = f'{TABLES_URL}/lobby'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
TITLE = '17개 행성의 추격전'
OPENING = '사이렌이 울린다. 망치를 든 드워프가 쫓아온다.'
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
PASSWORD = '열려라 참깨'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """로비를 보고 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def third(signing_key: SigningKey) -> dict[str, str]:
    """로비를 보고 들어오는 또 다른 사람의 머리말."""
    return bearer(signing_key, THIRD)


async def publish_scenario(client: AsyncClient, headers: dict[str, str], title: str = TITLE) -> dict:
    """게시할 조건을 갖춘 시나리오를 만들고 판을 하나 낸다. 시나리오를 돌려준다. 판의 번호는 1 이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {'title': title, 'rulebook_id': rulebook.json()['id'], 'openings': [OPENING], 'default_sheet': SHEET}
    scenario = await client.post(SCENARIOS_URL, json=body, headers=headers)
    assert scenario.status_code == status.HTTP_201_CREATED, scenario.text
    published = await client.post(f'{SCENARIOS_URL}/{scenario.json()["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    return scenario.json()


async def open_table(client: AsyncClient, headers: dict[str, str], scenario: dict | None = None, **fields) -> dict:
    """내 시나리오의 1번 판으로 테이블을 연다. 시나리오를 주지 않으면 새로 만든다. 기본은 로비에 보이는 2인 테이블."""
    scenario = scenario or await publish_scenario(client, headers)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, 'is_public': True}
    body.update(fields)
    response = await client.post(TABLES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def lobby(client: AsyncClient, headers: dict[str, str], **params) -> dict:
    """로비를 읽는다."""
    response = await client.get(LOBBY_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def join_url(table: dict) -> str:
    """로비에서 테이블에 들어가는 주소."""
    return f'{TABLES_URL}/{table["id"]}/join'


def ids(page: dict) -> list[str]:
    """목록에 실린 테이블들의 ID."""
    return [table['id'] for table in page['items']]


# --- 로그인 ---


@pytest.mark.parametrize(('method', 'path'), [('GET', '/lobby'), ('POST', f'/{NO_SUCH_ID}/join')])
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{TABLES_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 로비에 보일지는 만들 때 정한다 ---


async def test_a_table_is_hidden_from_the_lobby_unless_the_host_says_so(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    scenario = await publish_scenario(client, me)
    hidden = (
        await client.post(TABLES_URL, json={'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}, headers=me)
    ).json()
    shown = await open_table(client, me, scenario)

    page = await lobby(client, friend)

    # 정하지 않으면 보이지 않는다. 초대 코드로만 들어온다
    assert (hidden['is_public'], shown['is_public']) == (False, True)
    assert ids(page) == [shown['id']]
    assert page['total'] == 1


@pytest.mark.parametrize(
    'fields',
    [
        # 비밀번호는 로비에 보이는 테이블에만 건다
        {'is_public': False, 'password': PASSWORD},
        {'password': PASSWORD},
        {'is_public': True, 'password': '가' * (TABLE_PASSWORD_MIN_LENGTH - 1)},
        {'is_public': True, 'password': '가' * (TABLE_PASSWORD_MAX_LENGTH + 1)},
        {'is_public': True, 'password': ''},
        {'is_public': 'maybe'},
    ],
)
async def test_rejects_a_bad_lobby_setting(client: AsyncClient, me: dict[str, str], fields: dict):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, **fields}

    response = await client.post(TABLES_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_lobby_setting_cannot_be_changed_later(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    # 고치는 주소가 없다. 다르게 하고 싶으면 테이블을 새로 연다
    responses = [
        await client.patch(f'{TABLES_URL}/{table["id"]}', json={'is_public': False}, headers=me),
        await client.put(f'{TABLES_URL}/{table["id"]}', json={'is_public': False}, headers=me),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_405_METHOD_NOT_ALLOWED] * 2


# --- 로비에는 들어갈 수 있는 테이블만 나온다 ---


async def test_the_lobby_lists_the_newest_table_first(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    scenario = await publish_scenario(client, me)
    first = await open_table(client, me, scenario)
    second = await open_table(client, me, scenario, password=PASSWORD)

    page = await lobby(client, friend)
    one_per_page = await lobby(client, friend, limit=1, offset=1)

    assert ids(page) == [second['id'], first['id']]
    assert (ids(one_per_page), one_per_page['total']) == ([first['id']], 2)
    # 비밀번호가 걸렸는지는 알려 준다. 화면이 자물쇠를 그린다
    assert [table['has_password'] for table in page['items']] == [True, False]
    assert page['items'][0]['member_count'] == 1
    # 목록에는 초대 코드와 앉은 사람을 싣지 않는다
    assert set(page['items'][0]) == {
        'id',
        'title',
        'status',
        'rating',
        'capacity',
        'member_count',
        'host_id',
        'is_public',
        'has_password',
        'narration_style',
        'created_at',
    }


async def test_a_full_table_leaves_the_lobby(client: AsyncClient, me: dict[str, str], friend: dict, third: dict):
    table = await open_table(client, me, capacity=2)

    await client.post(join_url(table), json={}, headers=friend)
    full = await lobby(client, third)
    # 한 사람이 나가면 다시 보인다
    await client.delete(f'{TABLES_URL}/{table["id"]}/members/me', headers=friend)
    has_a_seat = await lobby(client, third)

    assert (ids(full), full['total']) == ([], 0)
    assert ids(has_a_seat) == [table['id']]


async def test_a_table_that_has_started_or_ended_leaves_the_lobby(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    scenario = await publish_scenario(client, me)
    started = await open_table(client, me, scenario)
    await client.put(f'{TABLES_URL}/{started["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{TABLES_URL}/{started["id"]}/start', headers=me)
    ended = await open_table(client, me, scenario)
    await client.post(f'{TABLES_URL}/{ended["id"]}/end', headers=me)
    recruiting = await open_table(client, me, scenario)

    page = await lobby(client, friend)

    assert ids(page) == [recruiting['id']]
    # 목록에 없는 테이블에는 이 길로 들어갈 수도 없다
    for table in (started, ended):
        response = await client.post(join_url(table), json={}, headers=friend)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()['reason'] == 'not_recruiting'


async def test_the_lobby_can_be_narrowed_to_one_scenario(client: AsyncClient, me: dict[str, str], friend: dict):
    chase = await publish_scenario(client, me)
    trial = await publish_scenario(client, me, title='17번째 재판')
    chase_table = await open_table(client, me, chase)
    trial_table = await open_table(client, me, trial)

    narrowed = await lobby(client, friend, scenario_id=trial['id'])
    unknown = await lobby(client, friend, scenario_id=NO_SUCH_ID)
    bad = await client.get(LOBBY_URL, params={'scenario_id': 'not-a-uuid'}, headers=friend)

    assert (ids(narrowed), narrowed['total']) == ([trial_table['id']], 1)
    assert narrowed['items'][0]['title'] == '17번째 재판'
    assert (ids(unknown), unknown['total']) == ([], 0)
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert set(ids(await lobby(client, friend))) == {chase_table['id'], trial_table['id']}


async def make_adult_table(session: AsyncSession) -> GameTable:
    """
    서비스를 거치지 않고, 로비에 보이는 성인용 4인 테이블을 저장한다.

    서비스로는 만들 수 없는 테이블이다(성인용은 혼자서만 한다). 등급으로 거르는 조건을 따로 확인하려고 만든다.
    """
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.flush()
    version = ScenarioVersion(scenario_id=scenario.asset_id, number=1, snapshot={})
    session.add(version)
    await session.flush()
    table = GameTable(host_id=ME, version_id=version.id, title='성인용', content={}, opening_index=0)
    table.capacity, table.rating, table.invite_code, table.is_public = TABLE_MAX_PLAYERS, 'adult', 'adult-code-1', True
    table.members = [TableMember(user_id=ME)]
    session.add(table)
    await session.commit()
    return table


async def test_an_adult_table_is_not_in_the_lobby(client: AsyncClient, friend: dict[str, str], session: AsyncSession):
    table = await make_adult_table(session)

    page = await lobby(client, friend)
    joined = await client.post(f'{TABLES_URL}/{table.id}/join', json={}, headers=friend)

    # 성인 인증이 생길 때까지 성인용 테이블은 아무에게도 보이지 않는다
    assert (ids(page), page['total']) == ([], 0)
    assert joined.status_code == status.HTTP_404_NOT_FOUND


# --- 초대 코드 없이 들어간다 ---


async def test_joins_a_table_from_the_lobby(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)

    response = await client.post(join_url(table), json={}, headers=friend)

    assert response.status_code == status.HTTP_200_OK
    joined = response.json()
    assert [member['user_id'] for member in joined['members']] == [str(ME), str(FRIEND)]
    # 들어온 사람에게 초대 코드는 보이지 않는다. GM 전용 글도 나가지 않는다
    assert joined['invite_code'] is None
    assert GM_GUIDE not in response.text


async def test_a_table_hidden_from_the_lobby_cannot_be_joined_without_the_invite_code(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    hidden = await open_table(client, me, is_public=False)

    by_id = await client.post(join_url(hidden), json={}, headers=friend)
    no_such_table = await client.post(f'{TABLES_URL}/{NO_SUCH_ID}/join', json={}, headers=friend)

    # ID 를 알아도 들어갈 수 없다. 있다는 것도 알려 주지 않는다
    assert by_id.status_code == status.HTTP_404_NOT_FOUND
    assert no_such_table.status_code == status.HTTP_404_NOT_FOUND
    assert by_id.json() == no_such_table.json()


async def test_the_seat_rules_are_the_same_as_with_an_invite_code(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], third: dict[str, str]
):
    table = await open_table(client, me, capacity=2)
    await client.post(join_url(table), json={}, headers=friend)

    again = await client.post(join_url(table), json={}, headers=friend)
    full = await client.post(join_url(table), json={}, headers=third)

    assert (again.status_code, again.json()['reason']) == (status.HTTP_409_CONFLICT, 'already_seated')
    assert (full.status_code, full.json()['reason']) == (status.HTTP_409_CONFLICT, 'table_full')


# --- 비밀번호 ---


async def test_a_password_keeps_strangers_out(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me, password=PASSWORD)

    wrong = await client.post(join_url(table), json={'password': '열려라 들깨'}, headers=friend)
    missing = await client.post(join_url(table), json={}, headers=friend)
    right = await client.post(join_url(table), json={'password': PASSWORD}, headers=friend)

    # 로비에 보이는 테이블이라 있다는 것은 누구나 안다. 그래서 404 가 아니라 403 이다
    assert wrong.status_code == status.HTTP_403_FORBIDDEN
    assert missing.status_code == status.HTTP_403_FORBIDDEN
    assert right.status_code == status.HTTP_200_OK
    assert right.json()['member_count'] == 2


@pytest.mark.parametrize('password', ['', '가', '가' * TABLE_PASSWORD_MAX_LENGTH, f' {PASSWORD}'])
async def test_a_wrong_password_of_any_shape_is_just_wrong(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], password: str
):
    table = await open_table(client, me, password=PASSWORD)

    response = await client.post(join_url(table), json={'password': password}, headers=friend)

    # 너무 짧다고 알려 주지 않는다. 비밀번호의 길이를 짐작할 실마리를 주지 않는다
    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_a_table_without_a_password_ignores_what_is_sent(client: AsyncClient, me: dict[str, str], friend: dict):
    table = await open_table(client, me)

    response = await client.post(join_url(table), json={'password': '아무거나'}, headers=friend)

    assert response.status_code == status.HTTP_200_OK


async def test_the_invite_code_needs_no_password(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me, password=PASSWORD)

    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

    # 초대 코드를 가진 사람은 방장이 직접 부른 사람이다
    assert response.status_code == status.HTTP_200_OK


async def test_the_password_is_never_stored_or_sent_as_written(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, 'is_public': True, 'password': PASSWORD}

    created = await client.post(TABLES_URL, json=body, headers=me)

    table = created.json()
    assert table['has_password'] is True
    # 방장에게도 돌려주지 않는다
    assert PASSWORD not in created.text
    assert PASSWORD not in (await client.get(f'{TABLES_URL}/{table["id"]}', headers=me)).text
    assert PASSWORD not in (await client.get(LOBBY_URL, headers=friend)).text
    # DB 에는 계산한 값만 있다
    stored = await session.scalar(text('SELECT password_hash FROM game_tables WHERE id = :id'), {'id': table['id']})
    assert PASSWORD not in stored
    assert stored.startswith('scrypt$')


@pytest.mark.parametrize('body', [{'password': '가' * (TABLE_PASSWORD_MAX_LENGTH + 1)}, {'invite_code': 'x'}])
async def test_rejects_a_bad_lobby_join(client: AsyncClient, me: dict[str, str], friend: dict[str, str], body: dict):
    table = await open_table(client, me)

    response = await client.post(join_url(table), json=body, headers=friend)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- DB 의 마지막 방어선 ---


async def test_the_database_rejects_a_password_on_a_hidden_table(session: AsyncSession):
    table = await make_adult_table(session)
    table.is_public = False
    table.password_hash = 'scrypt$1$1$1$c2FsdA==$a2V5'

    with pytest.raises(IntegrityError):
        await session.commit()
