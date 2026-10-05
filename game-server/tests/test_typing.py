# game-server/tests/test_typing.py

"""
"입력 중" 표시를 검증한다.

보는 것은 넷이다.
  - 알리면 테이블의 다른 사람들의 스트림에 온다. 자기 자신에게는 오지 않는다.
  - 저장하지 않는다. 번호가 없고, 끊겼다 돌아와도 다시 오지 않고, 채팅이나 이벤트에 남지 않는다.
  - 채팅을 쓸 수 있는 사람만, 쓸 수 있는 때에만 알릴 수 있다.
  - 너무 자주 보내면 버린다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.chat.typing import PRUNE_THRESHOLD, TYPING_INTERVAL_SECONDS, TypingThrottle
from app.main import API_PREFIX
from app.realtime.service import Cursor
from app.realtime.signals import Kind, Signal
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token
from tests.streaming import DeafSource

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')
OTHER_TABLE = uuid.UUID('bbbbbbbb-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
HELLO = '나는 엘프 할게. 바이크는 내가 몬다.'


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
def third(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 세 번째로 들어오는 사람의 머리말."""
    return bearer(signing_key, THIRD)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_trio(client: AsyncClient, *headers: dict[str, str]) -> dict:
    """첫 사람이 테이블을 열고 나머지가 들어온다. 이벤트가 사람 수만큼 적혀 있다."""
    host, *guests = headers
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=host)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=host)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=host)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 3}
    response = await client.post(TABLES_URL, json=body, headers=host)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    table = response.json()
    for guest in guests:
        joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=guest)
        assert joined.status_code == status.HTTP_200_OK, joined.text
    return table


async def type_(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    """입력 중이라고 알린다."""
    response = await client.post(table_url(table, '/messages/typing'), headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text


# --- 다른 사람들에게 온다 ---


async def test_typing_reaches_the_others_at_the_table(
    client: AsyncClient, me: dict, friend: dict, third: dict, connect
):
    table = await open_trio(client, me, friend, third)
    friends, thirds = connect(table, FRIEND, Cursor(events=3)), connect(table, THIRD, Cursor(events=3))
    await friends.settle()
    await thirds.settle()

    await type_(client, me, table)

    for reader in (friends, thirds):
        frame = await reader.next()
        assert frame.event == 'typing'
        assert json.loads(frame.data) == {'user_id': str(ME)}
        # 저장된 것이 아니다. id 가 없으니 받는 쪽의 "여기까지 받았다"가 움직이지 않는다
        assert frame.id is None


async def test_typing_does_not_come_back_to_the_one_typing(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_trio(client, me, friend)
    mine, friends = connect(table, ME, Cursor(events=2)), connect(table, FRIEND, Cursor(events=2))
    await mine.settle()
    await friends.settle()

    await type_(client, me, table)

    assert (await friends.next()).event == 'typing'
    # 자기가 입력 중이라는 것은 본인이 이미 안다
    assert await mine.is_quiet()


async def test_typing_does_not_reach_another_table(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_trio(client, me, friend)
    other = await open_trio(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await type_(client, me, other)

    assert await reader.is_quiet()


async def test_typing_comes_before_the_message_that_follows(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_trio(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await type_(client, me, table)
    await client.post(table_url(table, '/messages'), json={'content': HELLO}, headers=me)

    # 받는 쪽은 그 사람의 채팅이 오면 입력 중 표시를 지운다. 순서가 뒤집히면 지운 표시가 다시 뜬다
    typing, message = await reader.take(2)
    assert (typing.event, message.event) == ('typing', 'chat_message')
    assert message.id == '2-1'


# --- 저장하지 않는다 ---


async def test_typing_is_not_replayed_to_someone_who_comes_later(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_trio(client, me, friend)

    await type_(client, me, table)

    # 지나간 "입력 중"은 다시 오지 않는다. 처음부터 받겠다고 해도 저장된 것(이벤트 둘)만 온다
    reader = connect(table, FRIEND)
    frames = await reader.take(2)
    assert [frame.event for frame in frames] == ['table_event', 'table_event']
    assert await reader.is_quiet()


async def test_typing_leaves_nothing_in_chat_or_events(client: AsyncClient, me: dict, friend: dict):
    table = await open_trio(client, me, friend)
    events = (await client.get(table_url(table, '/events'), headers=me)).json()
    messages = (await client.get(table_url(table, '/messages'), headers=me)).json()

    await type_(client, me, table)

    assert (await client.get(table_url(table, '/events'), headers=me)).json() == events
    assert (await client.get(table_url(table, '/messages'), headers=me)).json() == messages


# --- 누가, 언제 ---


async def test_typing_requires_login(client: AsyncClient):
    response = await client.post(f'{TABLES_URL}/{NO_SUCH_ID}/messages/typing')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_only_those_seated_can_say_they_are_typing(
    client: AsyncClient, me: dict, friend: dict, stranger: dict, connect
):
    table = await open_trio(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    outsider = await client.post(table_url(table, '/messages/typing'), headers=stranger)
    missing = await client.post(f'{TABLES_URL}/{NO_SUCH_ID}/messages/typing', headers=me)

    assert outsider.status_code == status.HTTP_404_NOT_FOUND
    assert outsider.json() == missing.json()
    assert await reader.is_quiet()


async def test_cannot_type_at_an_ended_table(client: AsyncClient, me: dict, friend: dict):
    table = await open_trio(client, me, friend)
    await client.post(table_url(table, '/end'), headers=me)

    response = await client.post(table_url(table, '/messages/typing'), headers=friend)

    # 채팅을 쓸 수 없는 때에는 입력 중도 알릴 수 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'already_ended'


async def test_typing_does_not_reach_someone_who_was_kicked(
    client: AsyncClient, me: dict, friend: dict, connect, app: FastAPI
):
    table = await open_trio(client, me, friend)
    # 신호를 듣지 않는 스트림이다. 내보낸 것을 아직 모르는 채로 기다리고 있게 한다
    reader = connect(table, FRIEND, Cursor(events=2), source=DeafSource())
    await reader.settle()
    await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    # 입력 중 신호만 직접 넣어 깨운다
    app.state.hub.wake(Signal(table_id=uuid.UUID(table['id']), kind=Kind.TYPING, user_id=ME))

    # 깨어나서 보니 앉아 있지 않다. 입력 중은 보내지 않고 닫힌다는 것만 보낸다
    closed = await reader.next()
    assert (closed.event, json.loads(closed.data)) == ('closed', {'reason': 'not_seated'})
    assert await reader.next() is None


# --- 너무 자주 보내면 버린다 ---


async def test_typing_again_too_soon_is_dropped_silently(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_trio(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await type_(client, me, table)
    # 바로 또 보낸다. 보낸 쪽에는 똑같이 204 다
    await type_(client, me, table)

    assert (await reader.next()).event == 'typing'
    # 두 번째 것은 다른 사람들에게 가지 않았다
    assert await reader.is_quiet()


async def test_typing_again_after_the_interval_goes_out(
    client: AsyncClient, me: dict, friend: dict, connect, app: FastAPI
):
    table = await open_trio(client, me, friend)
    # 간격을 0 으로 둔다. 기다리지 않고도 "간격이 지난 뒤"가 된다
    app.state.typing_throttle = TypingThrottle(interval=0)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await type_(client, me, table)
    assert (await reader.next()).event == 'typing'
    await type_(client, me, table)

    assert (await reader.next()).event == 'typing'


def test_the_throttle_allows_one_per_interval():
    throttle = TypingThrottle()

    assert throttle.allow(TABLE, ME, now=100.0) is True
    assert throttle.allow(TABLE, ME, now=100.0 + TYPING_INTERVAL_SECONDS - 0.1) is False
    assert throttle.allow(TABLE, ME, now=100.0 + TYPING_INTERVAL_SECONDS) is True


def test_the_throttle_counts_each_person_and_each_table_apart():
    throttle = TypingThrottle()
    throttle.allow(TABLE, ME, now=100.0)

    # 다른 사람, 다른 테이블은 따로 센다
    assert throttle.allow(TABLE, FRIEND, now=100.0) is True
    assert throttle.allow(OTHER_TABLE, ME, now=100.0) is True
    assert throttle.allow(TABLE, ME, now=100.0) is False


def test_a_refused_attempt_does_not_push_the_next_one_back():
    throttle = TypingThrottle()
    throttle.allow(TABLE, ME, now=100.0)

    # 간격 안에 계속 두드려도, 처음 보낸 때로부터 간격이 지나면 다시 된다
    assert throttle.allow(TABLE, ME, now=101.0) is False
    assert throttle.allow(TABLE, ME, now=100.0 + TYPING_INTERVAL_SECONDS) is True


def test_the_throttle_forgets_old_records():
    throttle = TypingThrottle()
    for _ in range(PRUNE_THRESHOLD):
        throttle.allow(uuid.uuid4(), ME, now=100.0)

    # 기록이 가득 찼을 때 새 것이 오면, 간격이 지난 것을 치운다
    later = 100.0 + TYPING_INTERVAL_SECONDS
    assert throttle.allow(TABLE, ME, now=later) is True
    assert len(throttle._last_sent) == 1
