# game-server/tests/test_tables_api.py

"""
테이블을 검증한다. 만들기, 들어가기, 캐릭터, 나가기, 방장이 하는 일.

보는 것은 다섯이다.
  - 테이블은 판의 복사본으로 만들어진다. 남의 시나리오는 공개 중인 판으로만, 자기 시나리오는 어느 판으로든 만든다.
  - 테이블은 앉은 사람만 본다. GM 전용 글은 앉은 사람에게도 나가지 않는다.
  - 정원이 차면 더 앉을 수 없고, 프리젠 하나는 한 사람만 쓴다(동시에 오는 요청은 test_table_locking.py 가 본다).
  - 내보내기, 방장 넘기기, 시작, 끝내기는 방장만 한다.
  - 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다. 모두 나가면 테이블이 끝난다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import (
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    Asset,
    AssetType,
    Scenario,
    ScenarioVersion,
)
from app.main import API_PREFIX
from app.tables.models import INVITE_CODE_LENGTH, GameTable, TableMember
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
WORLDS_URL = f'{API_PREFIX}/worlds'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
TITLE = '17개 행성의 추격전'
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.', '법정이다. 17번째 사형 선고가 내려진다.']
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
GM_NOTES = '고속도로의 끝에는 아무것도 없다.'
PREGENS = [
    {'name': '폭주족 엘프', 'description': '귀가 길어서 헬멧을 못 쓴다.'},
    {'name': '악역영애', 'description': '바이크는 처음이지만 웃음소리는 크다.'},
]
# 시나리오에 넣을 때는 프리젠마다 시트가 있어야 게시된다
SCENARIO_PREGENS = [{**pregen, 'sheet': SHEET} for pregen in PREGENS]


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


@pytest.fixture
def third(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 또 다른 사람의 머리말."""
    return bearer(signing_key, THIRD)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def publish_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """게시할 조건을 갖춘 시나리오를 만들고 판을 하나 낸다. 시나리오를 돌려준다. 판의 번호는 1 이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {
        'title': TITLE,
        'rulebook_id': rulebook.json()['id'],
        'openings': OPENINGS,
        'pregens': SCENARIO_PREGENS,
        'default_sheet': SHEET,
    }
    body.update(fields)
    scenario = await client.post(SCENARIOS_URL, json=body, headers=headers)
    assert scenario.status_code == status.HTTP_201_CREATED, scenario.text
    published = await client.post(f'{SCENARIOS_URL}/{scenario.json()["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    return scenario.json()


async def make_public(client: AsyncClient, headers: dict[str, str], scenario: dict) -> None:
    """시나리오의 1번 판을 공개한다."""
    url = f'{SCENARIOS_URL}/{scenario["id"]}/listing'
    await client.patch(url, json={'tagline': '바이크와 엘프', 'genres': ['sf']}, headers=headers)
    response = await client.put(f'{url}/publication', json={'version': 1}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def open_table(client: AsyncClient, headers: dict[str, str], capacity: int = TABLE_MAX_PLAYERS, **fields) -> dict:
    """자기 시나리오를 만들어 그 1번 판으로 테이블을 연다. 테이블을 돌려준다."""
    scenario = await publish_scenario(client, headers, **fields)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': capacity}
    response = await client.post(TABLES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """초대 코드로 테이블에 들어간다. 들어간 사람이 보는 테이블을 돌려준다."""
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def set_character(client: AsyncClient, headers: dict[str, str], table: dict, **fields) -> dict:
    """캐릭터를 정한다."""
    response = await client.put(table_url(table, '/character'), json=fields, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """테이블을 읽는다."""
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def seated(table: dict) -> list[str]:
    """테이블에 앉은 사람들의 ID. 들어온 순서다."""
    return [member['user_id'] for member in table['members']]


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', ''),
        ('GET', ''),
        ('POST', '/join'),
        ('GET', f'/{NO_SUCH_ID}'),
        ('PUT', f'/{NO_SUCH_ID}/character'),
        ('DELETE', f'/{NO_SUCH_ID}/members/me'),
        ('DELETE', f'/{NO_SUCH_ID}/members/{NO_SUCH_ID}'),
        ('PUT', f'/{NO_SUCH_ID}/host'),
        ('POST', f'/{NO_SUCH_ID}/start'),
        ('POST', f'/{NO_SUCH_ID}/end'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{TABLES_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 만들기 ---


async def test_opens_a_table_from_my_own_version(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me, recommended_players={'min': 2, 'max': 3})

    response = await client.post(
        TABLES_URL, json={'scenario_id': scenario['id'], 'version': 1, 'capacity': 3}, headers=me
    )

    assert response.status_code == status.HTTP_201_CREATED
    table = response.json()
    assert table['title'] == TITLE
    assert table['status'] == 'recruiting'
    assert table['rating'] == 'all'
    assert table['capacity'] == 3
    assert table['recommended_players'] == {'min': 2, 'max': 3}
    # 고르지 않으면 첫 번째 스타팅이다
    assert table['opening'] == OPENINGS[0]
    assert table['pregens'] == [{**pregen, 'sheet': SHEET, 'taken_by': None} for pregen in PREGENS]
    # 만든 사람이 방장이 되어 앉는다. 캐릭터는 아직 없다
    assert table['host_id'] == str(ME)
    assert table['member_count'] == 1
    assert len(table['members']) == 1
    host = table['members'][0]
    assert (host['user_id'], host['is_host'], host['character'], host['pregen_index']) == (str(ME), True, None, None)
    assert len(table['invite_code']) == INVITE_CODE_LENGTH
    assert (table['started_at'], table['ended_at']) == (None, None)


async def test_the_response_carries_only_the_listed_fields(client: AsyncClient, me: dict[str, str]):
    world = (await client.post(WORLDS_URL, json={'title': '세계관', 'gm_notes': GM_NOTES}, headers=me)).json()

    table = await open_table(client, me, world_id=world['id'])

    assert set(table) == {
        'id',
        'title',
        'status',
        'rating',
        'capacity',
        'member_count',
        'host_id',
        'is_public',
        'has_password',
        'created_at',
        'opening',
        'recommended_players',
        'rules',
        'character_modes',
        'default_sheet',
        'player_made_hp',
        'pregens',
        'members',
        'invite_code',
        'started_at',
        'ended_at',
    }
    # GM 전용 글은 방장에게도 나가지 않는다. 남의 시나리오로 테이블을 여는 방장도 있다
    read_again = await client.get(table_url(table), headers=me)
    assert GM_GUIDE not in read_again.text
    assert GM_NOTES not in read_again.text


async def test_picks_an_opening(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1, 'opening_index': 1}

    response = await client.post(TABLES_URL, json=body, headers=me)

    assert response.json()['opening'] == OPENINGS[1]


async def test_an_opening_that_is_not_in_the_version_cannot_be_picked(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1, 'opening_index': len(OPENINGS)}

    response = await client.post(TABLES_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'opening_index' in response.json()['detail']


@pytest.mark.parametrize(
    'fields',
    [
        {'capacity': 0},
        {'capacity': TABLE_MAX_PLAYERS + 1},
        {'capacity': None},
        {'opening_index': -1},
        {'version': 0},
        {'scenario_id': 'not-a-uuid'},
        {'scenario_id': None},
        # 모르는 칸은 받지 않는다. 방장이나 상태를 직접 적을 수 없다
        {'host_id': str(STRANGER)},
        {'status': 'playing'},
    ],
)
async def test_rejects_a_bad_table(client: AsyncClient, me: dict[str, str], fields: dict):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, **fields}

    response = await client.post(TABLES_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_table_keeps_its_copy_when_the_draft_changes(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()

    # 테이블을 연 뒤에 초안을 고치고 새 판을 낸다
    changed = {'title': '바꾼 제목', 'openings': ['바꾼 도입부'], 'pregens': []}
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json=changed, headers=me)
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)

    # 테이블은 만들 때 복사해 온 것을 그대로 갖고 있다
    again = await read(client, me, table)
    assert again['title'] == TITLE
    assert again['opening'] == OPENINGS[0]
    assert len(again['pregens']) == len(PREGENS)


async def test_two_tables_from_one_version_are_separate(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}

    first = (await client.post(TABLES_URL, json=body, headers=me)).json()
    second = (await client.post(TABLES_URL, json=body, headers=me)).json()

    assert first['id'] != second['id']
    assert first['invite_code'] != second['invite_code']
    # 한 테이블에서 프리젠을 가져가도 다른 테이블의 것은 그대로다
    await set_character(client, me, first, pregen_index=0)
    assert (await read(client, me, second))['pregens'][0]['taken_by'] is None


async def test_a_version_in_an_old_format_is_copied_in_the_current_one(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    scenario = await publish_scenario(client, me)
    # 스타팅이 하나뿐이고 프리젠이 없던 때(형식 1)에 굳힌 판
    old = {'format': 1, 'title': '옛 판', 'description': '', 'rating': 'all', 'opening': '옛 도입부'}
    old.update(rulebook={'id': str(ME), 'title': '룰북', 'gm_guide': GM_GUIDE}, world=None, lorebooks=[])
    session.add(ScenarioVersion(scenario_id=uuid.UUID(scenario['id']), number=2, snapshot=old))
    await session.commit()

    response = await client.post(
        TABLES_URL, json={'scenario_id': scenario['id'], 'version': 2, 'capacity': 2}, headers=me
    )

    assert response.status_code == status.HTTP_201_CREATED
    table = response.json()
    assert (table['title'], table['opening'], table['pregens']) == ('옛 판', '옛 도입부', [])
    # 복사본은 지금의 모양으로 저장된다. 테이블을 읽는 코드는 옛 형식을 몰라도 된다
    stored = await session.scalar(text('SELECT content FROM game_tables WHERE id = :id'), {'id': table['id']})
    assert stored['openings'] == ['옛 도입부']
    assert 'opening' not in stored


# --- 어느 판으로 만들 수 있는가 ---


async def test_opens_a_table_from_someone_elses_public_scenario(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    scenario = await publish_scenario(client, me)
    await make_public(client, me, scenario)

    # 번호를 적지 않으면 공개 중인 판이다
    response = await client.post(TABLES_URL, json={'scenario_id': scenario['id'], 'capacity': 2}, headers=stranger)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['host_id'] == str(STRANGER)
    assert GM_GUIDE not in response.text


async def test_someone_elses_scenario_can_only_be_played_in_its_public_version(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    public = await publish_scenario(client, me)
    await make_public(client, me, public)
    not_public = await publish_scenario(client, me)

    # 공개하지 않은 시나리오는 없는 것으로 보인다
    hidden = await client.post(TABLES_URL, json={'scenario_id': not_public['id'], 'capacity': 2}, headers=stranger)
    # 번호를 적어 판을 고르는 것은 자기 시나리오일 때만 된다. 공개 중인 판의 번호여도 안 된다
    numbered = await client.post(
        TABLES_URL, json={'scenario_id': public['id'], 'version': 1, 'capacity': 2}, headers=stranger
    )

    assert hidden.status_code == status.HTTP_404_NOT_FOUND
    assert numbered.status_code == status.HTTP_404_NOT_FOUND


async def test_my_own_scenario_needs_a_version_that_exists(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me)

    # 공개하지 않았으니 번호 없이는 찾을 판이 없다
    no_number = await client.post(TABLES_URL, json={'scenario_id': scenario['id'], 'capacity': 2}, headers=me)
    no_such_version = await client.post(
        TABLES_URL, json={'scenario_id': scenario['id'], 'version': 2, 'capacity': 2}, headers=me
    )
    no_such_scenario = await client.post(
        TABLES_URL, json={'scenario_id': NO_SUCH_ID, 'version': 1, 'capacity': 2}, headers=me
    )

    assert no_number.status_code == status.HTTP_404_NOT_FOUND
    assert no_such_version.status_code == status.HTTP_404_NOT_FOUND
    assert no_such_scenario.status_code == status.HTTP_404_NOT_FOUND


async def test_an_adult_version_can_only_be_played_alone(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me, rating='adult')
    body = {'scenario_id': scenario['id'], 'version': 1}

    # 성인 인증이 없는 동안에는 제작자가 혼자 시험해 보는 것만 된다
    alone = await client.post(TABLES_URL, json={**body, 'capacity': 1}, headers=me)
    together = await client.post(TABLES_URL, json={**body, 'capacity': 2}, headers=me)

    assert alone.status_code == status.HTTP_201_CREATED
    assert alone.json()['rating'] == 'adult'
    assert together.status_code == status.HTTP_409_CONFLICT
    assert together.json()['reason'] == 'solo_only'


async def test_nobody_can_join_an_adult_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me, capacity=1, rating='adult')

    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

    # 자리가 없다고 알려 주지 않는다. 볼 수 없는 등급의 테이블은 없는 것으로 보인다
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- 들어가기 ---


async def test_joins_with_the_invite_code(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)

    joined = await join(client, friend, table)

    assert seated(joined) == [str(ME), str(FRIEND)]
    assert joined['member_count'] == 2
    assert [member['is_host'] for member in joined['members']] == [True, False]
    # 초대 코드는 방장에게만 보인다
    assert joined['invite_code'] is None
    assert (await read(client, me, table))['invite_code'] == table['invite_code']


@pytest.mark.parametrize('body', [{'invite_code': 'no-such-code'}, {'invite_code': ''}, {}, {'table_id': NO_SUCH_ID}])
async def test_a_wrong_invite_code_opens_nothing(client: AsyncClient, me: dict[str, str], friend: dict, body: dict):
    await open_table(client, me)

    response = await client.post(f'{TABLES_URL}/join', json=body, headers=friend)

    assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT)


async def test_cannot_sit_twice(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    again = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_seated'
    assert (await read(client, me, table))['member_count'] == 2


async def test_a_full_table_takes_no_one(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], third: dict[str, str]
):
    table = await open_table(client, me, capacity=2)
    await join(client, friend, table)

    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=third)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'table_full'


async def test_a_table_that_has_started_or_ended_takes_no_one(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    started = await open_table(client, me)
    await set_character(client, me, started, name='엘프')
    await client.post(table_url(started, '/start'), headers=me)
    ended = await open_table(client, me)
    await client.post(table_url(ended, '/end'), headers=me)

    for table in (started, ended):
        response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()['reason'] == 'not_recruiting'


# --- 테이블은 앉은 사람만 본다 ---


async def test_a_table_looks_like_it_does_not_exist_to_those_not_seated(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    table = await open_table(client, me)
    body = {'name': '불청객'}

    responses = [
        await client.get(table_url(table), headers=stranger),
        await client.put(table_url(table, '/character'), json=body, headers=stranger),
        await client.delete(table_url(table, '/members/me'), headers=stranger),
        await client.delete(table_url(table, f'/members/{ME}'), headers=stranger),
        await client.put(table_url(table, '/host'), json={'user_id': str(STRANGER)}, headers=stranger),
        await client.post(table_url(table, '/start'), headers=stranger),
        await client.post(table_url(table, '/end'), headers=stranger),
    ]

    # 403 이 아니라 404 다. 테이블이 있다는 것을 알려 주지 않는다
    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * len(responses)
    assert (await read(client, me, table))['status'] == 'recruiting'


async def test_lists_only_the_tables_i_sit_at(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    first = await open_table(client, me)
    second = await open_table(client, me)
    await join(client, friend, second)

    mine = (await client.get(TABLES_URL, headers=me)).json()
    theirs = (await client.get(TABLES_URL, headers=friend)).json()
    one_per_page = (await client.get(TABLES_URL, params={'limit': 1}, headers=me)).json()

    # 최근에 만든 것부터다
    assert [table['id'] for table in mine['items']] == [second['id'], first['id']]
    assert mine['total'] == 2
    assert [table['id'] for table in theirs['items']] == [second['id']]
    assert theirs['items'][0]['member_count'] == 2
    assert (len(one_per_page['items']), one_per_page['total']) == (1, 2)
    # 목록에는 초대 코드와 앉은 사람을 싣지 않는다
    assert set(mine['items'][0]) == {
        'id',
        'title',
        'status',
        'rating',
        'capacity',
        'member_count',
        'host_id',
        'is_public',
        'has_password',
        'created_at',
    }


# --- 캐릭터 ---


async def test_makes_a_character_of_my_own(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    changed = await set_character(client, me, table, name='  떠돌이 요리사  ', description='칼보다 국자를 잘 쓴다.')

    member = changed['members'][0]
    assert member['character'] == {'name': '떠돌이 요리사', 'description': '칼보다 국자를 잘 쓴다.'}
    assert member['pregen_index'] is None
    # 직접 만든 캐릭터는 프리젠을 차지하지 않는다
    assert [pregen['taken_by'] for pregen in changed['pregens']] == [None, None]


async def test_takes_a_pregen(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    changed = await set_character(client, me, table, pregen_index=1)

    member = changed['members'][0]
    assert member['character'] == PREGENS[1]
    assert member['pregen_index'] == 1
    assert [pregen['taken_by'] for pregen in changed['pregens']] == [None, str(ME)]


async def test_a_pregen_can_be_rewritten_but_stays_taken(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)

    # 프리젠을 가져오면서 이름을 고쳐 쓴다. 적지 않은 설명은 프리젠의 것이다
    changed = await set_character(client, me, table, pregen_index=0, name='은퇴한 폭주족')
    taken = await client.put(table_url(table, '/character'), json={'pregen_index': 0}, headers=friend)

    assert changed['members'][0]['character'] == {'name': '은퇴한 폭주족', 'description': PREGENS[0]['description']}
    # 이름을 바꿔도 그 자리는 내 것이다. 같은 인물이 둘이 될 수 없다
    assert taken.status_code == status.HTTP_409_CONFLICT
    assert taken.json()['reason'] == 'pregen_taken'


async def test_changing_the_character_frees_the_pregen(client: AsyncClient, me: dict[str, str], friend: dict):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, me, table, pregen_index=0)

    # 같은 프리젠을 다시 고르는 것은 된다
    await set_character(client, me, table, pregen_index=0, description='다시 썼다.')
    # 직접 만든 캐릭터로 바꾸면 프리젠이 풀린다
    await set_character(client, me, table, name='떠돌이 요리사')
    freed = await set_character(client, friend, table, pregen_index=0)

    assert freed['pregens'][0]['taken_by'] == str(FRIEND)
    mine = freed['members'][0]
    # 통째로 바뀐다. 앞의 설명이 남지 않는다
    assert mine['character'] == {'name': '떠돌이 요리사', 'description': ''}
    assert mine['pregen_index'] is None


@pytest.mark.parametrize(
    'body',
    [
        # 프리젠을 고르지 않았으면 이름이 있어야 한다
        {},
        {'description': '이름이 없다'},
        {'name': '   '},
        {'name': '가' * (CHARACTER_NAME_MAX_LENGTH + 1)},
        {'name': '엘프', 'description': '가' * (CHARACTER_DESCRIPTION_MAX_LENGTH + 1)},
        {'pregen_index': -1},
        # 판에 없는 프리젠
        {'pregen_index': len(PREGENS)},
        # 캐릭터에는 정해 둔 칸만 있다. 숫자는 엔진이 생길 때 엔진이 관리한다
        {'name': '엘프', 'hp': 9999},
    ],
)
async def test_rejects_a_bad_character(client: AsyncClient, me: dict[str, str], body: dict):
    table = await open_table(client, me)

    response = await client.put(table_url(table, '/character'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await read(client, me, table))['members'][0]['character'] is None


async def test_the_character_cannot_change_after_the_table_starts(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, name='엘프')
    await client.post(table_url(table, '/start'), headers=me)

    response = await client.put(table_url(table, '/character'), json={'name': '드워프'}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_recruiting'
    assert (await read(client, me, table))['members'][0]['character']['name'] == '엘프'


# --- 나가기 ---


async def test_leaves_the_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, friend, table, pregen_index=0)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    again = await client.delete(table_url(table, '/members/me'), headers=friend)

    assert left.status_code == status.HTTP_204_NO_CONTENT
    # 나간 사람에게는 없는 테이블이다
    assert again.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(table_url(table), headers=friend)).status_code == status.HTTP_404_NOT_FOUND
    after = await read(client, me, table)
    assert seated(after) == [str(ME)]
    # 가져갔던 프리젠이 풀린다
    assert after['pregens'][0]['taken_by'] is None


async def test_the_earliest_member_becomes_host_when_the_host_leaves(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], third: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await join(client, third, table)

    await client.delete(table_url(table, '/members/me'), headers=me)

    after = await read(client, friend, table)
    assert after['host_id'] == str(FRIEND)
    assert seated(after) == [str(FRIEND), str(THIRD)]
    assert after['status'] == 'recruiting'
    # 새 방장에게 초대 코드가 보인다
    assert after['invite_code'] == table['invite_code']
    assert (await read(client, third, table))['invite_code'] is None


async def test_the_table_ends_when_the_last_member_leaves(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)

    await client.delete(table_url(table, '/members/me'), headers=me)

    stored = await session.get(GameTable, uuid.UUID(table['id']))
    assert stored.status == 'ended'
    assert stored.ended_at is not None
    assert stored.members == []
    # 끝난 테이블에는 초대 코드로도 들어올 수 없다
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert response.status_code == status.HTTP_409_CONFLICT


# --- 방장이 하는 일 ---


async def test_only_the_host_runs_the_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    responses = [
        await client.delete(table_url(table, f'/members/{ME}'), headers=friend),
        await client.put(table_url(table, '/host'), json={'user_id': str(FRIEND)}, headers=friend),
        await client.post(table_url(table, '/start'), headers=friend),
        await client.post(table_url(table, '/end'), headers=friend),
    ]

    # 앉아 있는 사람은 테이블이 있다는 것을 이미 안다. 그래서 404 가 아니라 403 이다
    assert [response.status_code for response in responses] == [status.HTTP_403_FORBIDDEN] * len(responses)
    after = await read(client, me, table)
    assert (after['host_id'], after['status'], seated(after)) == (str(ME), 'recruiting', [str(ME), str(FRIEND)])


async def test_kicking_a_member_changes_the_invite_code(client: AsyncClient, me: dict[str, str], friend: dict):
    table = await open_table(client, me)
    await join(client, friend, table)

    response = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    assert response.status_code == status.HTTP_200_OK
    after = response.json()
    assert seated(after) == [str(ME)]
    assert after['invite_code'] != table['invite_code']
    assert (await client.get(table_url(table), headers=friend)).status_code == status.HTTP_404_NOT_FOUND
    # 내보낸 사람이 옛 코드로 다시 들어오지 못한다. 새 코드를 받은 사람은 들어온다
    old_code = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert old_code.status_code == status.HTTP_404_NOT_FOUND
    assert seated(await join(client, friend, after)) == [str(ME), str(FRIEND)]


async def test_the_host_cannot_kick_someone_who_is_not_seated_or_themself(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)

    not_seated = await client.delete(table_url(table, f'/members/{STRANGER}'), headers=me)
    myself = await client.delete(table_url(table, f'/members/{ME}'), headers=me)

    assert not_seated.status_code == status.HTTP_404_NOT_FOUND
    assert myself.status_code == status.HTTP_409_CONFLICT
    assert myself.json()['reason'] == 'cannot_kick_self'
    after = await read(client, me, table)
    # 아무도 내보내지 않았으면 초대 코드도 그대로다
    assert (seated(after), after['invite_code']) == ([str(ME), str(FRIEND)], table['invite_code'])


async def test_hands_the_table_over(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    response = await client.put(table_url(table, '/host'), json={'user_id': str(FRIEND)}, headers=me)
    to_stranger = await client.put(table_url(table, '/host'), json={'user_id': str(STRANGER)}, headers=friend)

    assert response.status_code == status.HTTP_200_OK
    # 넘긴 사람은 더는 방장이 아니다. 초대 코드도 보이지 않는다
    assert (response.json()['host_id'], response.json()['invite_code']) == (str(FRIEND), None)
    assert (await read(client, friend, table))['invite_code'] == table['invite_code']
    # 앉아 있지 않은 사람에게는 넘길 수 없다
    assert to_stranger.status_code == status.HTTP_404_NOT_FOUND
    # 넘긴 사람도 그대로 앉아 있다
    assert seated(await read(client, me, table)) == [str(ME), str(FRIEND)]


async def test_starts_when_everyone_has_a_character(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)
    await set_character(client, me, table, pregen_index=0)

    too_early = await client.post(table_url(table, '/start'), headers=me)
    await set_character(client, friend, table, name='떠돌이 요리사')
    started = await client.post(table_url(table, '/start'), headers=me)
    again = await client.post(table_url(table, '/start'), headers=me)

    assert too_early.status_code == status.HTTP_409_CONFLICT
    assert too_early.json()['reason'] == 'characters_missing'
    assert started.status_code == status.HTTP_200_OK
    assert started.json()['status'] == 'playing'
    assert started.json()['started_at'] is not None
    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'not_recruiting'


async def test_ends_the_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    ended = await client.post(table_url(table, '/end'), headers=me)
    responses = [
        await client.post(table_url(table, '/end'), headers=me),
        await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me),
        await client.put(table_url(table, '/host'), json={'user_id': str(FRIEND)}, headers=me),
    ]

    assert ended.status_code == status.HTTP_200_OK
    assert ended.json()['status'] == 'ended'
    assert ended.json()['ended_at'] is not None
    # 끝난 테이블은 바꿀 수 없다
    assert [response.status_code for response in responses] == [status.HTTP_409_CONFLICT] * len(responses)
    assert [response.json()['reason'] for response in responses] == ['already_ended'] * len(responses)
    # 읽는 것과 나가는 것은 된다
    assert seated(await read(client, friend, table)) == [str(ME), str(FRIEND)]
    assert (await client.delete(table_url(table, '/members/me'), headers=friend)).status_code == 204


# --- DB 의 마지막 방어선 ---


async def make_table(session: AsyncSession, **fields) -> GameTable:
    """서비스를 거치지 않고 테이블 하나를 만든다. 아직 저장하지 않는다."""
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.flush()
    version = ScenarioVersion(scenario_id=scenario.asset_id, number=1, snapshot={})
    session.add(version)
    await session.flush()
    values = {'host_id': ME, 'version_id': version.id, 'title': '테이블', 'content': {}, 'opening_index': 0}
    values.update(capacity=2, rating='all', invite_code='test-code-01')
    values.update(fields)
    table = GameTable(**values)
    session.add(table)
    return table


@pytest.mark.parametrize(
    'fields',
    [
        {'capacity': 0},
        {'capacity': TABLE_MAX_PLAYERS + 1},
        {'status': 'paused'},
        {'rating': 'teen'},
        {'opening_index': -1},
    ],
)
async def test_the_database_rejects_a_bad_table(session: AsyncSession, fields: dict):
    await make_table(session, **fields)

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_two_members_with_the_same_pregen(session: AsyncSession):
    table = await make_table(session)
    table.members = [
        TableMember(user_id=ME, character_name='엘프', pregen_index=0),
        TableMember(user_id=FRIEND, character_name='엘프', pregen_index=0),
    ]

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_allows_many_characters_without_a_pregen(session: AsyncSession):
    table = await make_table(session)
    table.members = [TableMember(user_id=ME, character_name='엘프'), TableMember(user_id=FRIEND, character_name='엘프')]

    # 프리젠을 쓰지 않은 캐릭터끼리는 겹치는 것으로 보지 않는다
    await session.commit()


async def test_the_database_rejects_a_pregen_without_a_character(session: AsyncSession):
    table = await make_table(session)
    table.members = [TableMember(user_id=ME, pregen_index=0)]

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_two_tables_with_the_same_invite_code(session: AsyncSession):
    await make_table(session)
    await make_table(session)

    with pytest.raises(IntegrityError):
        await session.commit()
