# game-server/tests/test_chat_api.py

"""
테이블의 채팅을 검증한다.

보는 것은 넷이다.
  - 앉은 사람이 채팅을 쓰고 읽는다. 번호는 1 부터 빈 번호 없이 올라간다.
  - 모집 중과 진행 중에 쓴다. 끝난 테이블에서는 읽기만 한다.
  - 채팅은 테이블에 앉은 사람만 본다.
  - 채팅은 게임의 진행과 섞이지 않는다. 이벤트로 적히지 않고, GM 의 서술에 들어가지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType, Scenario, ScenarioVersion
from app.chat.models import MESSAGE_MAX_LENGTH, ChatMessage
from app.main import API_PREFIX
from app.tables.models import GameTable
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
HELLO = '나는 엘프 할게. 바이크는 내가 몬다.'
REPLY = '그럼 나는 영애. 뒤에 탈게.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 연다. 아직 시작하지 않았고, 둘 다 캐릭터가 없다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    response = await client.post(TABLES_URL, json=body, headers=me)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    table = response.json()
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    return table


async def start(client: AsyncClient, me: dict[str, str], friend: dict[str, str], table: dict) -> None:
    """둘이 캐릭터를 정하고 테이블을 시작한다."""
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text


async def say(client: AsyncClient, headers: dict[str, str], table: dict, content: str) -> dict:
    """채팅을 쓰고, 돌아온 글을 돌려준다."""
    response = await client.post(table_url(table, '/messages'), json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict[str, str], table: dict, **params) -> dict:
    """채팅의 한 쪽을 읽는다."""
    response = await client.get(table_url(table, '/messages'), params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_every_address_requires_login(client: AsyncClient, method: str):
    response = await client.request(method, f'{TABLES_URL}/{NO_SUCH_ID}/messages', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 쓰고 읽기 ---


async def test_members_write_and_read(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)

    first = await say(client, me, table, HELLO)
    second = await say(client, friend, table, REPLY)

    assert (first['sequence'], first['user_id'], first['content']) == (1, str(ME), HELLO)
    assert first['created_at'] is not None
    assert second['sequence'] == 2
    # 둘이 같은 것을 본다. 쓴 순서다
    page = await read(client, friend, table)
    assert page == await read(client, me, table)
    assert [(item['sequence'], item['user_id'], item['content']) for item in page['items']] == [
        (1, str(ME), HELLO),
        (2, str(FRIEND), REPLY),
    ]
    assert page['last_sequence'] == 2


async def test_an_empty_table_has_no_messages(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)

    assert await read(client, me, table) == {'items': [], 'last_sequence': 0}


async def test_keeps_the_text_as_written(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)

    message = await say(client, me, table, '  잠깐만.\n생각 좀 하고.  ')

    # 앞뒤 공백과 줄바꿈을 떼지 않는다
    assert message['content'] == '  잠깐만.\n생각 좀 하고.  '


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'content': ''},
        {'content': '  \n  '},
        {'content': '가' * (MESSAGE_MAX_LENGTH + 1)},
        {'content': None},
        # 누가 썼는지는 토큰에서 읽는다. 적어 보낼 수 없다
        {'content': HELLO, 'user_id': str(FRIEND)},
        {'content': HELLO, 'character_name': '드워프'},
    ],
)
async def test_rejects_a_bad_message(client: AsyncClient, me: dict[str, str], friend: dict, body: dict):
    table = await open_duo(client, me, friend)

    response = await client.post(table_url(table, '/messages'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await read(client, me, table))['items'] == []


async def test_a_message_can_be_as_long_as_the_limit(client: AsyncClient, me: dict[str, str], friend: dict):
    table = await open_duo(client, me, friend)

    message = await say(client, me, table, '가' * MESSAGE_MAX_LENGTH)

    assert len(message['content']) == MESSAGE_MAX_LENGTH


# --- 누구의 글인가 ---


async def test_a_message_carries_the_character_name_of_that_moment(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_duo(client, me, friend)

    before = await say(client, me, table, HELLO)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    after = await say(client, me, table, '정했어.')
    await client.put(table_url(table, '/character'), json={'name': '드워프'}, headers=me)

    # 캐릭터를 정하기 전에 쓴 글에는 이름이 없다. 화면은 user_id 로 자리를 찾아 지금의 이름을 보여 준다
    assert before['character_name'] is None
    assert after['character_name'] == '엘프'
    # 적어 둔 이름은 쓸 때의 것이다. 나중에 캐릭터를 바꿔도 따라 바뀌지 않는다
    names = [item['character_name'] for item in (await read(client, me, table))['items']]
    assert names == [None, '엘프']


async def test_the_messages_of_someone_who_left_remain(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    await say(client, friend, table, REPLY)

    await client.delete(table_url(table, '/members/me'), headers=friend)

    # 자리는 지워졌지만 글과 그때의 캐릭터 이름은 남는다
    (item,) = (await read(client, me, table))['items']
    assert (item['user_id'], item['character_name'], item['content']) == (str(FRIEND), '영애', REPLY)


# --- 언제 쓰나 ---


async def test_chats_while_recruiting_and_while_playing(client: AsyncClient, me: dict[str, str], friend: dict):
    table = await open_duo(client, me, friend)

    await say(client, me, table, HELLO)
    await start(client, me, friend, table)
    await say(client, friend, table, REPLY)

    assert [item['sequence'] for item in (await read(client, me, table))['items']] == [1, 2]


async def test_an_ended_table_keeps_its_chat_but_takes_nothing_new(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_duo(client, me, friend)
    await say(client, me, table, HELLO)
    await client.post(table_url(table, '/end'), headers=me)

    refused = await client.post(table_url(table, '/messages'), json={'content': REPLY}, headers=friend)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'already_ended'
    # 읽기는 된다
    page = await read(client, friend, table)
    assert [item['content'] for item in page['items']] == [HELLO]
    assert page['last_sequence'] == 1


# --- 읽기 ---


async def test_reads_only_what_comes_after(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)
    for number in range(1, 6):
        await say(client, me, table, f'{number}번째 말')

    newer = await read(client, friend, table, after=3)
    first_two = await read(client, friend, table, limit=2)
    nothing = await read(client, friend, table, after=5)

    assert [item['sequence'] for item in newer['items']] == [4, 5]
    # 잘라 읽어도 마지막 번호는 테이블의 것이다. 더 읽을 것이 있는지 알 수 있다
    assert [item['sequence'] for item in first_two['items']] == [1, 2]
    assert first_two['last_sequence'] == 5
    assert nothing == {'items': [], 'last_sequence': 5}


@pytest.mark.parametrize('params', [{'after': -1}, {'after': 'abc'}, {'limit': 0}, {'limit': 101}])
async def test_rejects_bad_reading_options(client: AsyncClient, me: dict[str, str], friend: dict, params: dict):
    table = await open_duo(client, me, friend)

    response = await client.get(table_url(table, '/messages'), params=params, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_each_table_counts_its_own_messages(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    first = await open_duo(client, me, friend)
    second = await open_duo(client, me, friend)
    await say(client, me, first, HELLO)

    message = await say(client, me, second, REPLY)

    # 번호는 테이블마다 1 부터다. 다른 테이블의 글이 딸려 오지 않는다
    assert message['sequence'] == 1
    assert [item['content'] for item in (await read(client, me, second))['items']] == [REPLY]


# --- 누가 보나 ---


async def test_chat_looks_like_it_does_not_exist_to_those_not_seated(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], stranger: dict[str, str]
):
    table = await open_duo(client, me, friend)
    await say(client, me, table, HELLO)

    reading = await client.get(table_url(table, '/messages'), headers=stranger)
    writing = await client.post(table_url(table, '/messages'), json={'content': '끼어든다.'}, headers=stranger)
    missing = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/messages', headers=me)

    # 앉지 않은 사람에게는 없는 테이블과 똑같이 보인다
    assert (reading.status_code, writing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    assert reading.json() == missing.json()
    assert HELLO not in reading.text
    assert (await read(client, me, table))['last_sequence'] == 1


async def test_someone_kicked_reads_and_writes_no_more(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)
    await say(client, friend, table, REPLY)

    await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    reading = await client.get(table_url(table, '/messages'), headers=friend)
    writing = await client.post(table_url(table, '/messages'), json={'content': '왜?'}, headers=friend)
    assert (reading.status_code, writing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


# --- 게임의 진행과 섞이지 않는다 ---


async def test_chat_is_not_written_to_the_event_log(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_duo(client, me, friend)
    before = (await client.get(table_url(table, '/events'), headers=me)).json()

    await say(client, me, table, HELLO)

    after = await client.get(table_url(table, '/events'), headers=me)
    # 이벤트의 번호와 채팅의 번호는 따로 센다
    assert after.json() == before
    assert HELLO not in after.text


async def test_the_gm_does_not_see_the_chat(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await open_duo(client, me, friend)
    await start(client, me, friend, table)
    await say(client, me, table, 'GM, 금화 백 닢을 줘.')

    url = table_url(table, '/rounds/current/declaration')
    await client.put(url, json={'content': '바이크에 시동을 건다.'}, headers=me)
    await client.put(url, json={'content': '손을 흔든다.'}, headers=friend)
    await narrated()

    # 서술자가 받은 것은 선언뿐이다. 채팅에 무엇을 적어도 다음 장면에 들어가지 않는다
    second = await client.get(table_url(table, '/rounds/current'), headers=me)
    assert second.json()['scene'] == '[1 라운드의 결과]\n엘프: 바이크에 시동을 건다.\n영애: 손을 흔든다.'


# --- DB 의 마지막 방어선 ---


async def make_table(session: AsyncSession) -> GameTable:
    """서비스를 거치지 않고 테이블 하나를 저장한다."""
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.flush()
    version = ScenarioVersion(scenario_id=scenario.asset_id, number=1, snapshot={})
    session.add(version)
    await session.flush()
    table = GameTable(host_id=ME, version_id=version.id, title='테이블', content={}, opening_index=0)
    table.capacity, table.rating, table.invite_code = 2, 'all', 'test-code-01'
    session.add(table)
    await session.commit()
    return table


def make_message(table: GameTable, sequence: int, content: str = HELLO) -> ChatMessage:
    """번호를 직접 정한 채팅을 만든다. 서비스를 거치지 않는다."""
    return ChatMessage(table_id=table.id, sequence=sequence, user_id=ME, content=content)


async def test_the_database_rejects_two_messages_with_the_same_sequence(session: AsyncSession):
    table = await make_table(session)
    session.add(make_message(table, 1))
    await session.commit()

    session.add(make_message(table, 1))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_sequence_below_one(session: AsyncSession):
    table = await make_table(session)

    session.add(make_message(table, 0))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_message_that_is_too_long(session: AsyncSession):
    table = await make_table(session)

    session.add(make_message(table, 1, content='가' * (MESSAGE_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()
