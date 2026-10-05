# game-server/tests/test_stream.py

"""
테이블의 스트림을 검증한다. 진짜 PostgreSQL 의 NOTIFY 로 신호가 오간다.

HTTP 를 거치지 않고 스트림을 만드는 함수(service.stream)를 직접 돌린다.
테스트용 클라이언트는 응답이 끝나야 결과를 돌려주는데, 스트림은 끝나지 않기 때문이다.
HTTP 쪽(인증, 404, 머리말)은 tests/test_stream_api.py 가 본다.

보는 것은 다섯이다.
  - 붙으면 밀린 것부터 받고, 그 뒤로는 생기는 대로 받는다.
  - 신호는 커밋된 것만 알린다. 신호가 끊겨도 주기적으로 직접 읽어서 따라잡는다.
  - 끊겼다 돌아오면 못 본 것부터 이어 받는다. 같은 것을 두 번 받지 않는다.
  - 앉아 있지 않게 되면, 테이블이 끝나면, 토큰이 만료되면 서버가 닫는다.
  - 열려 있는 라운드의 남의 선언은 스트림으로도 오지 않는다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.main import API_PREFIX
from app.realtime import service, signals
from app.realtime.service import Cursor
from app.realtime.signals import Kind, Signal
from app.realtime.sse import Frame
from app.tables import repository as table_repository
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token, make_viewer
from tests.streaming import DeafSource

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

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


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 연다. 이벤트가 둘(만들어짐, 들어옴) 적혀 있다."""
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
    """둘이 캐릭터를 정하고 테이블을 시작한다. 이벤트가 셋(시작, 서술, 열림) 더 적힌다."""
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text


async def say(client: AsyncClient, headers: dict[str, str], table: dict, content: str) -> None:
    """채팅을 쓴다."""
    response = await client.post(table_url(table, '/messages'), json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


def kinds(frames: list[Frame]) -> list[str]:
    """메시지들의 종류. 이벤트는 그 안의 type 까지 적는다."""
    return [json.loads(frame.data).get('type', frame.event) for frame in frames]


# --- 밀린 것과 새 것 ---


async def test_a_new_stream_gets_what_is_already_there(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    await say(client, me, table, HELLO)

    reader = connect(table, FRIEND)

    assert await reader.next_comment() == 'connected'
    frames = await reader.take(3)
    assert kinds(frames) == ['table_created', 'member_joined', 'chat_message']
    # id 는 "여기까지 받았다"다. 이벤트 번호와 채팅 번호를 함께 적는다
    assert [frame.id for frame in frames] == ['1-0', '2-0', '2-1']
    assert json.loads(frames[2].data)['content'] == HELLO
    assert await reader.is_quiet()


async def test_a_new_chat_message_arrives_at_once(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await say(client, me, table, HELLO)

    # 스트림이 스스로 깨어나는 것은 60 초 뒤다. 그 전에 왔으니 신호를 받아서 온 것이다
    frame = await reader.next()
    assert (frame.event, frame.id) == ('chat_message', '2-1')
    message = json.loads(frame.data)
    assert (message['sequence'], message['user_id'], message['content']) == (1, str(ME), HELLO)


async def test_new_events_arrive_at_once_in_order(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await start(client, me, friend, table)

    frames = await reader.take(3)
    assert kinds(frames) == ['table_started', 'gm_narration', 'round_opened']
    assert [frame.id for frame in frames] == ['3-0', '4-0', '5-0']
    assert json.loads(frames[1].data)['payload'] == {'text': OPENINGS[0]}


async def test_everyone_at_the_table_gets_it(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    mine, friends = connect(table, ME, Cursor(events=2)), connect(table, FRIEND, Cursor(events=2))
    await mine.settle()
    await friends.settle()

    await say(client, me, table, HELLO)

    # 쓴 사람에게도 온다. 화면은 번호를 보고 이미 띄운 글인지 안다
    assert (await mine.next()).id == '2-1'
    assert (await friends.next()).id == '2-1'


async def test_another_table_does_not_wake_this_one(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    other = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await say(client, me, other, HELLO)

    assert await reader.is_quiet()


async def test_another_persons_declaration_does_not_come_while_the_round_is_open(
    client: AsyncClient, me: dict, friend: dict, connect
):
    table = await open_duo(client, me, friend)
    await start(client, me, friend, table)
    reader = connect(table, FRIEND, Cursor(events=5))
    await reader.settle()

    url = table_url(table, '/rounds/current/declaration')
    await client.put(url, json={'content': '바이크에 시동을 건다.'}, headers=me)

    # 선언은 라운드가 닫힐 때 이벤트가 된다. 그 전에는 스트림으로도 오지 않는다
    assert await reader.is_quiet()

    await client.put(url, json={'content': '손을 흔든다.'}, headers=friend)

    frames = await reader.take(5)
    assert kinds(frames) == ['player_action', 'player_action', 'round_closed', 'gm_narration', 'round_opened']


# --- 신호 ---


async def test_a_change_that_is_rolled_back_sends_no_signal(
    client: AsyncClient, me: dict, friend: dict, connect, session: AsyncSession
):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    # 이벤트를 적고 신호까지 보냈지만 커밋하지 않고 되돌린다
    locked = await table_repository.lock_table(session, uuid.UUID(table['id']))
    recorder.record(session, locked, EventType.TABLE_ENDED, actor_id=ME)
    await signals.publish(session, Signal(table_id=locked.id, kind=Kind.EVENTS))
    await session.flush()
    await session.rollback()

    # 저장되지 않은 것은 알리지도 않는다
    assert await reader.is_quiet()


async def test_the_stream_catches_up_by_itself_when_signals_are_lost(
    client: AsyncClient, me: dict, friend: dict, connect
):
    table = await open_duo(client, me, friend)
    # 신호를 듣지 않는다. 대신 0.2 초마다 스스로 깨어난다
    reader = connect(table, FRIEND, Cursor(events=2), source=DeafSource(), heartbeat=0.2)
    assert await reader.next_comment() == 'connected'

    await say(client, me, table, HELLO)

    # 깨어날 때마다 주석을 보내고 DB 를 직접 읽는다. 신호 없이도 새 글이 온다
    assert await reader.next_comment() == 'ping'
    assert (await reader.next()).id == '2-1'


# --- 이어 받기 ---


async def test_coming_back_picks_up_where_it_left_off(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    await say(client, me, table, '첫 글')
    first = connect(table, FRIEND)
    last = (await first.take(3))[-1]
    assert last.id == '2-1'

    # 끊긴 사이에 채팅 하나와 이벤트 셋이 생긴다
    await first.close()
    await say(client, me, table, '끊긴 사이의 글')
    await start(client, me, friend, table)

    # 마지막으로 받은 id 를 들고 다시 붙는다
    events, messages = (int(number) for number in last.id.split('-'))
    again = connect(table, FRIEND, Cursor(events=events, messages=messages))

    frames = await again.take(4)
    # 못 본 것만 온다. 이미 받은 것이 다시 오지 않는다
    assert kinds(frames) == ['table_started', 'gm_narration', 'round_opened', 'chat_message']
    assert frames[-1].id == '5-2'
    assert await again.is_quiet()


async def test_a_long_backlog_is_read_in_batches(
    client: AsyncClient, me: dict, friend: dict, connect, monkeypatch: pytest.MonkeyPatch
):
    table = await open_duo(client, me, friend)
    for number in range(1, 6):
        await say(client, me, table, f'{number}번째 말')
    # 한 번에 둘씩만 읽게 한다. 다섯을 다 보내려면 세 번 읽어야 한다
    monkeypatch.setattr(service, 'READ_BATCH', 2)

    reader = connect(table, FRIEND, Cursor(events=2))

    frames = await reader.take(5)
    assert [frame.id for frame in frames] == ['2-1', '2-2', '2-3', '2-4', '2-5']


# --- 서버가 닫는다 ---


async def test_being_kicked_closes_the_stream(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    # 내보내진 사람에게는 그 뒤의 것이 가지 않는다. 내보냈다는 이벤트도 가지 않는다
    closed = await reader.next()
    assert (closed.event, closed.id) == ('closed', None)
    assert json.loads(closed.data) == {'reason': 'not_seated'}
    # 스트림이 끝난다
    assert await reader.next() is None


async def test_leaving_closes_the_stream(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await client.delete(table_url(table, '/members/me'), headers=friend)

    assert json.loads((await reader.next()).data) == {'reason': 'not_seated'}
    assert await reader.next() is None


async def test_the_table_ending_closes_the_stream_after_the_last_event(
    client: AsyncClient, me: dict, friend: dict, connect
):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await client.post(table_url(table, '/end'), headers=me)

    # 끝났다는 이벤트까지는 보내고 닫는다
    ended, closed = await reader.take(2)
    assert kinds([ended]) == ['table_ended']
    assert json.loads(closed.data) == {'reason': 'table_ended'}
    assert await reader.next() is None


async def test_the_stream_closes_when_the_token_expires(client: AsyncClient, me: dict, friend: dict, connect):
    table = await open_duo(client, me, friend)
    # 0.3 초 뒤에 만료되는 토큰으로 붙는다. 스트림이 스스로 깨어나는 것은 60 초 뒤다
    reader = connect(table, FRIEND, Cursor(events=2), viewer=make_viewer(FRIEND, seconds=0.3))
    assert await reader.next_comment() == 'connected'

    # 신호가 없어도 만료되는 때에 맞춰 깨어나 닫는다
    closed = await reader.next()
    assert json.loads(closed.data) == {'reason': 'token_expired'}
    assert await reader.next() is None


# --- 자리를 치운다 ---


async def test_disconnecting_frees_the_seat(client: AsyncClient, me: dict, friend: dict, connect, app: FastAPI):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    assert await reader.next_comment() == 'connected'
    assert app.state.hub.count(uuid.UUID(table['id'])) == 1

    await reader.close()

    # 받는 쪽이 끊으면 방송실의 자리가 치워진다. 치우지 않으면 떠난 연결이 쌓인다
    assert app.state.hub.count(uuid.UUID(table['id'])) == 0


async def test_a_closed_stream_frees_the_seat(client: AsyncClient, me: dict, friend: dict, connect, app: FastAPI):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))

    await client.post(table_url(table, '/end'), headers=me)
    await reader.take(2)
    assert await reader.next() is None

    assert app.state.hub.count(uuid.UUID(table['id'])) == 0


async def test_all_streams_share_one_listening_connection(client: AsyncClient, me: dict, friend: dict, connect, app):
    table = await open_duo(client, me, friend)
    first, second = connect(table, ME, Cursor(events=2)), connect(table, FRIEND, Cursor(events=2))
    assert await first.next_comment() == 'connected'
    assert await second.next_comment() == 'connected'

    # 스트림이 몇이든 듣는 연결은 하나다
    source = app.state.signal_source
    assert source.is_listening()
    connection = source._connection
    await source.ensure_listening()
    assert source._connection is connection
